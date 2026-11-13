"""Offline, backed-up migration of merchant numbers across all three stores."""
import json
import sqlite3
import secrets
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .common import encode
from .control import ControlStore


def migrate_identifiers(control_path, gateway_path, wallet_path, config_path=None, bootstrap_paths=()):
    paths = [Path(path).resolve() for path in (control_path, gateway_path, wallet_path)]
    if len(set(paths)) != 3 or not all(path.is_file() for path in paths):
        raise ValueError('Migration requires three distinct existing databases.')
    # Upgrade schema before attaching. Services must be stopped by the caller.
    ControlStore(paths[0])
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup_root = paths[0].parent / ('identifier-backup-' + stamp)
    backup_root.mkdir()
    for index, path in enumerate(paths):
        with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup_root / f'{index}-{path.name}')) as target:
            source.backup(target)
    db = sqlite3.connect(paths[0], isolation_level=None)
    db.row_factory = sqlite3.Row
    schemas = ('main', 'gateway', 'wallet')
    try:
        db.execute('PRAGMA foreign_keys=ON')
        for schema, path in zip(schemas[1:], paths[1:]):
            db.execute('ATTACH DATABASE ? AS ' + schema, (str(path),))
        # DELETE journals allow SQLite's super-journal to cover attached stores.
        # Restore WAL after the offline transaction finishes.
        for schema in schemas:
            db.execute(f'PRAGMA {schema}.wal_checkpoint(TRUNCATE)')
            if db.execute(f'PRAGMA {schema}.journal_mode=DELETE').fetchone()[0] != 'delete':
                raise RuntimeError('Stop all merchant services before migrating databases.')
        db.execute('BEGIN IMMEDIATE')
        db.execute('PRAGMA defer_foreign_keys=ON')
        db.execute('CREATE TABLE IF NOT EXISTS merchant_id_migrations(old_id TEXT PRIMARY KEY,new_id TEXT NOT NULL UNIQUE)')
        rows = db.execute("SELECT id FROM merchants WHERE id NOT GLOB 'GTT[0-9][0-9][0-9][0-9][0-9][0-9]' ORDER BY created_at,rowid").fetchall()
        for row in rows:
            old, new = row['id'], ControlStore.allocate_merchant_id(db)
            db.execute('UPDATE merchants SET id=? WHERE id=?', (new, old))
            for schema in schemas:
                tables = [row[0] for row in db.execute(f'SELECT name FROM {schema}.sqlite_master WHERE type=?', ('table',))]
                for table in tables:
                    quoted = '"' + table.replace('"', '""') + '"'
                    columns = {row[1] for row in db.execute(f'PRAGMA {schema}.table_info({quoted})')}
                    if 'merchant_id' in columns:
                        db.execute(f'UPDATE {schema}.{quoted} SET merchant_id=? WHERE merchant_id=?', (new, old))
            db.execute("UPDATE admin_audit SET target=? WHERE target=? AND action LIKE 'merchant.%'", (new, old))
            db.execute('INSERT INTO merchant_id_migrations VALUES (?,?)', (old, new))
            ControlStore.audit(db, 'system', 'merchant.identifier.migrate', new, details={'merchant_id': new, 'old_id': old, 'new_id': new})
        mapping = dict(db.execute('SELECT old_id,new_id FROM merchant_id_migrations'))
        def transform(value):
            if isinstance(value, list):
                return [transform(child) for child in value]
            if not isinstance(value, dict):
                return value
            result = {key: transform(child) for key, child in value.items()}
            for key in ('merchant_id',):
                if isinstance(result.get(key), str):
                    result[key] = mapping.get(result[key], result[key])
            if 'wallet_url' in result and isinstance(result.get('id'), str):
                result['id'] = mapping.get(result['id'], result['id'])
            return result
        for schema in schemas:
            tables = [row[0] for row in db.execute(f'SELECT name FROM {schema}.sqlite_master WHERE type=?', ('table',))]
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                json_columns = [row[1] for row in db.execute(f'PRAGMA {schema}.table_info({quoted})') if row[1].endswith('_json')]
                for column in json_columns:
                    # JSON may contain merchant metadata, never rewrite player IDs or arbitrary strings.
                    records = db.execute(f'SELECT rowid,"{column}" FROM {schema}.{quoted} WHERE "{column}" IS NOT NULL').fetchall()
                    for record in records:
                        original = json.loads(record[1])
                        changed = transform(original)
                        if changed != original:
                            db.execute(f'UPDATE {schema}.{quoted} SET "{column}"=? WHERE rowid=?', (encode(changed), record[0]))
        for schema in schemas:
            if db.execute(f'PRAGMA {schema}.foreign_key_check').fetchall():
                raise RuntimeError('Foreign key validation failed; rolling back migration.')
        db.commit()
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        for schema in schemas:
            try:
                db.execute(f'PRAGMA {schema}.journal_mode=WAL')
            except sqlite3.Error:
                pass
        db.close()
    store = ControlStore(paths[0])
    names = {merchant['id']: merchant['name'] for merchant in store.merchants()}
    provisioned = []
    for merchant in store.merchants():
        if not any(user['role'] == 'merchant_admin' for user in store.users(merchant['id'])):
            result = store.create_user('system', 'owner_' + secrets.token_hex(16), 'merchant_admin', merchant_id=merchant['id'])
            credentials = paths[0].parent / ('merchant-' + merchant['id'] + '-bootstrap.json')
            with credentials.open('x', encoding='utf-8') as stream:
                json.dump({'username': merchant['name'], 'password': result['temporary_password'], 'merchant_id': merchant['id'], 'url': 'http://127.0.0.1:8112/merchant/'}, stream, ensure_ascii=False, indent=2)
            provisioned.append(str(credentials))
    for path in [*([config_path] if config_path else []), *bootstrap_paths]:
        path = Path(path)
        if not path.is_file():
            continue
        raw = path.read_bytes()
        value = json.loads(raw)
        for key in ('sandbox_merchant', 'merchant_id'):
            if key in value:
                value[key] = mapping.get(value[key], value[key])
        if path in [Path(p) for p in bootstrap_paths] and value.get('merchant_id') in names:
            value['username'] = names[value['merchant_id']]
        if value != json.loads(raw):
            (backup_root / path.name).write_bytes(raw)
            temporary = path.with_suffix(path.suffix + '.migrating')
            temporary.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())
            temporary.replace(path)
    return {'mapping': mapping, 'backup': str(backup_root), 'provisioned_credentials': provisioned}
