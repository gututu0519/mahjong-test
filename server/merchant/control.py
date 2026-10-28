"""Database-backed merchant configuration, administrator sessions and audit trail."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from collections.abc import Mapping
from urllib.parse import urlsplit

from server.core.contracts import ServiceError
from .common import Database, encode, identifier, limit
from .identifiers import game_code, game_number

PERMISSIONS = {
    'admin': ('merchants.read', 'merchants.write', 'keys.rotate', 'games.read', 'transactions.read',
              'transactions.retry', 'audit.read', 'users.manage', 'rtp.read', 'rtp.write', 'rtp.manage'),
    'operator': ('merchants.read', 'games.read', 'transactions.read', 'transactions.retry', 'audit.read', 'rtp.read'),
    'viewer': ('merchants.read', 'games.read', 'transactions.read', 'audit.read', 'rtp.read'),
    'merchant_admin': ('merchants.read', 'profile.write', 'keys.rotate', 'games.read', 'transactions.read',
                       'transactions.retry', 'audit.read', 'users.manage', 'rtp.read', 'rtp.write'),
    'merchant_operator': ('merchants.read', 'games.read', 'transactions.read', 'transactions.retry', 'audit.read', 'rtp.read'),
    'merchant_viewer': ('merchants.read', 'games.read', 'transactions.read', 'audit.read', 'rtp.read'),
}


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ServiceError('PASSWORD_INVALID', '密码长度须为 12–128 个字符。')
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def password_matches(password, stored):
    if not isinstance(password, str) or len(password) > 128:
        return False
    _, iterations, salt, expected = stored.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(actual, expected)


def wallet_origin(value):
    if not isinstance(value, str) or len(value) > 512:
        raise ServiceError('WALLET_URL_INVALID', '请输入有效的钱包服务地址。')
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError:
        raise ServiceError('WALLET_URL_INVALID', '钱包端口无效。') from None
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path or (parsed.scheme != 'https' and not
               (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')))):
        raise ServiceError('WALLET_URL_INVALID', '钱包地址须为 HTTPS origin；本机可使用 loopback HTTP。')
    return value


def username(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}', value):
        raise ServiceError('USERNAME_INVALID', '用户名须为 3–40 位字母、数字、_、. 或 -。')
    return value.lower()


class ControlStore(Database):
    def __init__(self, path):
        super().__init__(path)
        with self.connection(True) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_fp_settings'").fetchone():
                db.execute('ALTER TABLE merchant_fp_settings RENAME TO merchant_prebet_settings')
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS merchants (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL,
                    wallet_url TEXT NOT NULL, currency TEXT NOT NULL, minor_unit INTEGER NOT NULL,
                    games_json TEXT NOT NULL, api_secret TEXT NOT NULL, wallet_secret TEXT NOT NULL,
                    version INTEGER NOT NULL, key_version INTEGER NOT NULL,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL, enabled INTEGER NOT NULL, auth_version INTEGER NOT NULL,
                    created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES admin_users(id),
                    auth_version INTEGER NOT NULL, csrf_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL, last_seen INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_login_limits (
                    bucket TEXT PRIMARY KEY, failures INTEGER NOT NULL, until_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL,
                    outcome TEXT NOT NULL, details_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS merchant_prebet_settings (
                    merchant_id TEXT PRIMARY KEY REFERENCES merchants(id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL,url TEXT NOT NULL,operator_token TEXT NOT NULL,secret_key TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS merchant_signing_credentials (
                    merchant_id TEXT PRIMARY KEY REFERENCES merchants(id) ON DELETE CASCADE,
                    secret TEXT NOT NULL,mode TEXT NOT NULL,version INTEGER NOT NULL,ready INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS control_counters (name TEXT PRIMARY KEY,value INTEGER NOT NULL);
            ''')
        with self.connection(True) as db:
            if 'merchant_id' not in {r['name'] for r in db.execute('PRAGMA table_info(admin_users)')}:
                db.execute('ALTER TABLE admin_users ADD COLUMN merchant_id TEXT REFERENCES merchants(id)')
            if 'merchant_id' not in {r['name'] for r in db.execute('PRAGMA table_info(admin_audit)')}:
                db.execute('ALTER TABLE admin_audit ADD COLUMN merchant_id TEXT')
                db.execute("UPDATE admin_audit SET merchant_id=target WHERE action LIKE 'merchant.%' AND target IN (SELECT id FROM merchants)")
                db.execute("UPDATE admin_audit SET merchant_id=json_extract(details_json,'$.merchant_id') WHERE merchant_id IS NULL")
            db.execute('CREATE INDEX IF NOT EXISTS audit_merchant_seq ON admin_audit(merchant_id,seq)')
            if 'login_user_id' not in {r['name'] for r in db.execute('PRAGMA table_info(merchants)')}:
                db.execute('ALTER TABLE merchants ADD COLUMN login_user_id TEXT')
            # Fail visibly on ambiguous names instead of authenticating another tenant.
            duplicates = db.execute('SELECT name FROM merchants GROUP BY lower(name) HAVING COUNT(*)>1').fetchall()
            if duplicates:
                raise ServiceError('MERCHANT_NAME_CONFLICT', '已有商户名称重复，请先为商户设置唯一登录名称。', 409)
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS merchant_login_name ON merchants(lower(name))')
            db.execute("UPDATE merchants SET login_user_id=(SELECT id FROM admin_users WHERE merchant_id=merchants.id AND role='merchant_admin' AND enabled=1 ORDER BY created_at,id LIMIT 1) WHERE login_user_id IS NULL")
            self.ensure_signing_credentials(db)
        # Used for a comparable password-check cost for unknown usernames.
        self.dummy_hash = password_hash('not-a-real-admin-password', '0' * 32)

    @staticmethod
    def audit(db, actor, action, target, outcome='success', details=None):
        details = details or {}
        scope = details.get('merchant_id')
        if not scope and action.startswith('merchant.'):
            row = db.execute('SELECT id FROM merchants WHERE id=?', (target,)).fetchone()
            scope = row['id'] if row else None
        if not scope:
            row = db.execute('SELECT merchant_id FROM admin_users WHERE username=?', (target if action.startswith('user.') else actor,)).fetchone()
            scope = row['merchant_id'] if row else None
        db.execute('INSERT INTO admin_audit(created_at,actor,action,target,outcome,details_json,merchant_id) VALUES (?,?,?,?,?,?,?)',
                   (int(time.time()), actor, action, target, outcome, encode(details), scope))

    @staticmethod
    def merchant_value(row, private=False):
        if row is None:
            return None
        value = {key: row[key] for key in ('id', 'name', 'wallet_url', 'currency', 'minor_unit',
                                          'version', 'key_version', 'created_at', 'updated_at')}
        codes = json.loads(row['games_json'])
        value.update(enabled=bool(row['enabled']), games=codes if private else [game_number(code) for code in codes], login_username=row['login_username'])
        value.update(signing_mode='unified', merchant_key_version=row['signing_version'] or 0,
                     merchant_key_fingerprint=hashlib.sha256(row['signing_secret'].encode()).hexdigest()[:12] if row['signing_secret'] else None)
        value['pre_payout'] = {'enabled': bool(row['prebet_enabled']), 'url': row['prebet_url'] or ''}
        if private:
            value['merchant_secret'] = row['signing_secret']
        return value

    def migrate(self, merchants):
        with self.connection(True) as db:
            for merchant_id, merchant in merchants.items():
                identifier(merchant_id, 'merchant_id')
                now = int(time.time())
                secret = merchant.get('merchant_secret') or secrets.token_hex(32)
                if not isinstance(secret, str) or not re.fullmatch(r'[0-9a-f]{64}', secret):
                    raise ServiceError('MERCHANT_SECRET_INVALID', '配置中的商户密钥无效。')
                result = db.execute('INSERT OR IGNORE INTO merchants(id,name,enabled,wallet_url,currency,minor_unit,games_json,api_secret,wallet_secret,version,key_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (merchant_id, merchant.get('name', merchant_id), bool(merchant['enabled']),
                     wallet_origin(merchant['wallet_url']), merchant['currency'], merchant['minor_unit'],
                     encode(merchant['games']), secret, secret, 1, 1, now, now))
                if result.rowcount:
                    db.execute('INSERT INTO merchant_signing_credentials VALUES (?,?,?,?,?)', (merchant_id, secret, 'unified', 1, 0))
                    if 'pre_payout' in merchant:
                        settings = merchant['pre_payout']
                        self.save_prebet(db, merchant_id, {'enabled': settings['enabled'], 'url': settings.get('url', '')})
                    self.audit(db, 'system', 'merchant.migrate', merchant_id)
            self.ensure_signing_credentials(db)

    def ensure_signing_credentials(self, db):
        # Normalize old local storage once; the runtime has only one signing mode.
        rows = db.execute("SELECT m.id,s.secret,s.version FROM merchants m LEFT JOIN merchant_signing_credentials s ON m.id=s.merchant_id WHERE s.merchant_id IS NULL OR s.secret='' OR s.mode<>'unified' OR s.ready<>0").fetchall()
        for row in rows:
            secret = row['secret'] or secrets.token_hex(32)
            db.execute('INSERT INTO merchant_signing_credentials VALUES (?,?,?,?,?) ON CONFLICT(merchant_id) DO UPDATE SET secret=excluded.secret,mode=excluded.mode,ready=0',
                       (row['id'], secret, 'unified', row['version'] or 1, 0))
            db.execute('UPDATE merchants SET api_secret=?,wallet_secret=?,version=version+1,updated_at=? WHERE id=?', (secret, secret, int(time.time()), row['id']))
            self.audit(db, 'system', 'merchant.signing.initialize', row['id'], details={'fingerprint': hashlib.sha256(secret.encode()).hexdigest()[:12]})
        db.execute("UPDATE merchant_prebet_settings SET operator_token='',secret_key='' WHERE operator_token<>'' OR secret_key<>''")
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchant_prebet_deliveries'").fetchone():
            db.execute('DELETE FROM merchant_prebet_deliveries')

    def merchants(self):
        with self.connection() as db:
            return [self.merchant_value(row) for row in db.execute(self.merchant_query() + ' ORDER BY m.created_at,m.id')]

    @staticmethod
    def merchant_query():
        return """SELECT m.*,f.enabled AS prebet_enabled,f.url AS prebet_url,
                  s.secret AS signing_secret,s.version AS signing_version,u.username AS login_username
                  FROM merchants m LEFT JOIN merchant_prebet_settings f ON m.id=f.merchant_id
                  LEFT JOIN merchant_signing_credentials s ON m.id=s.merchant_id
                  LEFT JOIN admin_users u ON m.login_user_id=u.id"""

    @staticmethod
    def allocate_merchant_id(db):
        last = db.execute("SELECT COALESCE(MAX(CAST(substr(id,4) AS INTEGER)),0) FROM merchants WHERE id GLOB 'GTT[0-9][0-9][0-9][0-9][0-9][0-9]'").fetchone()[0]
        counter = db.execute("SELECT value FROM control_counters WHERE name='merchant'").fetchone()
        number = max(last, counter[0] if counter else 0) + 1
        if number > 999999:
            raise ServiceError('MERCHANT_ID_EXHAUSTED', '六位商户编号已分配完毕。', 409)
        db.execute("INSERT INTO control_counters VALUES ('merchant',?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (number,))
        return f'GTT{number:06d}'

    @staticmethod
    def unique_name(db, name, merchant_id=None):
        if db.execute('SELECT 1 FROM merchants WHERE lower(name)=lower(?) AND id<>?', (name, merchant_id or '')).fetchone():
            raise ServiceError('MERCHANT_NAME_CONFLICT', '商户名称已被使用，请使用唯一的登录名称。', 409)
        if db.execute("SELECT 1 FROM admin_users WHERE lower(username)=lower(?) AND role LIKE 'merchant_%' AND id<>COALESCE((SELECT login_user_id FROM merchants WHERE id=?),'')", (name, merchant_id or '')).fetchone():
            raise ServiceError('MERCHANT_NAME_CONFLICT', '商户名称与团队登录名冲突，请使用其他名称。', 409)

    def merchant_row(self, db, merchant_id):
        return db.execute(self.merchant_query() + ' WHERE m.id=?', (merchant_id,)).fetchone()

    def merchant(self, merchant_id, private=False):
        with self.connection() as db:
            return self.merchant_value(self.merchant_row(db, merchant_id), private)

    def save_prebet(self, db, merchant_id, value, allow_rtp_transition=False):
        if not isinstance(value, dict) or type(value.get('enabled')) is not bool:
            raise ServiceError('PREBET_CONFIG_INVALID', '请核对平台预派彩设置。')
        if 'operator_token' in value or 'secret_key' in value:
            raise ServiceError('UNIFIED_SIGNING', '预派彩统一使用 merchant_secret，只需配置接口地址。')
        from .prebet import prebet_url
        url = value.get('url', '')
        if not isinstance(url, str):
            raise ServiceError('PREBET_CONFIG_INVALID', '请输入有效的接口地址。')
        if url:
            prebet_url(url)
        if value['enabled'] and not url:
            raise ServiceError('PREBET_CONFIG_INVALID', '启用预派彩需要填写接口地址。')
        rtp_path = getattr(self, 'rtp_database', None)
        if value['enabled'] and rtp_path and not allow_rtp_transition:
            read = sqlite3.connect(Path(rtp_path).resolve().as_uri() + '?mode=ro', uri=True)
            try:
                mode = read.execute('SELECT mode FROM rtp_modes WHERE merchant_id=?', (merchant_id,)).fetchone()
                old = db.execute('SELECT enabled FROM merchant_prebet_settings WHERE merchant_id=?', (merchant_id,)).fetchone()
                targets = read.execute("SELECT 1 FROM rtp_policies WHERE model_id IS NOT NULL AND (merchant_id=? OR scope='platform') LIMIT 1", (merchant_id,)).fetchone()
                if mode and mode[0] == 'rtp' or not mode and targets and not (old and old[0]):
                    raise ServiceError('RTP_MODE_CONFLICT', '已有 RTP 配置，请在 RTP 中心明确切换到平台预派彩模式。', 409)
            finally:
                read.close()
        db.execute('INSERT OR REPLACE INTO merchant_prebet_settings VALUES (?,?,?,?,?)', (merchant_id, value['enabled'], url, '', ''))

    def save_merchant(self, actor, payload, games, create=False):
        if payload.get('signing_mode', 'unified') != 'unified':
            raise ServiceError('SIGNING_MODE_INVALID', '当前仅使用统一签名。')
        if 'merchant_secret' in payload:
            raise ServiceError('MERCHANT_SECRET_AUTOMATIC', 'merchant_secret 由 GTT 自动生成，无需填写。')
        if create and 'id' in payload:
            raise ServiceError('MERCHANT_ID_AUTOMATIC', '商户号由系统自动生成，无需填写。')
        merchant_id = None if create else identifier(payload.get('id'), 'merchant_id')
        name = payload.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
            raise ServiceError('NAME_INVALID', '商户名称须为 1–80 个可见字符。')
        enabled = payload.get('enabled')
        selected = payload.get('games')
        if (type(enabled) is not bool or not isinstance(selected, list)
                or any(type(value) is not int for value in selected)
                or len(selected) != len(set(selected))):
            raise ServiceError('MERCHANT_INVALID', '请核对商户状态与游戏授权。')
        selected = [game_code(value) for value in selected]
        allowed = {game_code(value) if type(value) is int else value for value in games}
        if set(selected) - allowed:
            raise ServiceError('MERCHANT_INVALID', '游戏尚未接入商户网关。')
        origin = wallet_origin(payload.get('wallet_url'))
        now = int(time.time())
        keys = None
        with self.connection(True) as db:
            self.unique_name(db, name.strip(), merchant_id)
            old = None
            if create:
                currency = payload.get('currency', 'USD')
                if currency != 'USD':
                    raise ServiceError('CURRENCY_INVALID', '目前仅支持美元（USD）。')
                # The write transaction serializes ID allocation and insertion.
                # Existing legacy/generated IDs are never reused or overwritten.
                merchant_id = self.allocate_merchant_id(db)
                merchant_secret = secrets.token_hex(32)
                keys = {'merchant_secret': merchant_secret}
                db.execute('INSERT INTO merchants(id,name,enabled,wallet_url,currency,minor_unit,games_json,api_secret,wallet_secret,version,key_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (merchant_id, name.strip(), enabled, origin, currency, 100, encode(selected),
                     merchant_secret, merchant_secret, 1, 1, now, now))
                db.execute('INSERT INTO merchant_signing_credentials VALUES (?,?,?,?,?)', (merchant_id, merchant_secret, 'unified', 1, 0))
                password = secrets.token_urlsafe(24)
                user_id = secrets.token_hex(16)
                account = 'owner_' + user_id
                db.execute('INSERT INTO admin_users(id,username,password_hash,role,enabled,auth_version,created_at,merchant_id) VALUES (?,?,?,?,?,?,?,?)',
                           (user_id, account, password_hash(password), 'merchant_admin', 1, 1, now, merchant_id))
                db.execute('UPDATE merchants SET login_user_id=? WHERE id=?', (user_id, merchant_id))
            else:
                old = self.merchant_row(db, merchant_id)
                if old is None:
                    raise ServiceError('NOT_FOUND', '商户不存在。', 404)
                self.check_version(payload, old)
                if payload.get('currency', old['currency']) != old['currency']:
                    raise ServiceError('CURRENCY_IMMUTABLE', '已有商户的币种不可变更。')
                db.execute('UPDATE merchants SET name=?,enabled=?,wallet_url=?,games_json=?,version=version+1,updated_at=? WHERE id=?',
                           (name.strip(), enabled, origin, encode(selected), now, merchant_id))
            if create or 'pre_payout' in payload:
                self.save_prebet(db, merchant_id, payload.get('pre_payout', {'enabled': False, 'url': ''}))
            new = self.merchant_row(db, merchant_id)
            result = self.merchant_value(new)
            self.audit(db, actor, 'merchant.create' if create else 'merchant.update', merchant_id,
                       details={'before': self.merchant_value(old), 'after': result})
        return {'merchant': result, **({'keys': keys, 'login': {'name': name.strip(), 'temporary_password': password}} if keys else {})}

    @staticmethod
    def check_version(payload, row):
        if type(payload.get('version')) is not int or payload['version'] != row['version']:
            raise ServiceError('VERSION_CONFLICT', '配置已被修改，请刷新后重试。', 409)

    def rotate_keys(self, actor, payload):
        return self.manage_signing(actor, payload, 'rotate')

    def save_profile(self, actor, merchant_id, payload):
        # Authorization fields are owned by GTT, even for a merchant administrator.
        if set(payload) - {'id', 'version', 'name', 'wallet_url', 'pre_payout'}:
            raise ServiceError('FORBIDDEN', '商户只能修改自己的接入资料，不能变更平台授权。', 403)
        if payload.get('id', merchant_id) != merchant_id:
            raise ServiceError('FORBIDDEN', '不能访问其他商户。', 403)
        with self.connection(True) as db:
            old = self.merchant_row(db, merchant_id)
            if old is None:
                raise ServiceError('NOT_FOUND', '商户不存在。', 404)
            self.check_version(payload, old)
            name = payload.get('name', old['name'])
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
                raise ServiceError('NAME_INVALID', '商户名称须为 1–80 个可见字符。')
            self.unique_name(db, name.strip(), merchant_id)
            origin = wallet_origin(payload.get('wallet_url', old['wallet_url']))
            db.execute('UPDATE merchants SET name=?,wallet_url=?,version=version+1,updated_at=? WHERE id=?',
                       (name.strip(), origin, int(time.time()), merchant_id))
            if 'pre_payout' in payload:
                self.save_prebet(db, merchant_id, payload['pre_payout'])
            result = self.merchant_value(self.merchant_row(db, merchant_id))
            self.audit(db, actor, 'merchant.profile.update', merchant_id,
                       details={'before': self.merchant_value(old), 'after': result})
        return {'merchant': result}

    def manage_signing(self, actor, payload, action):
        merchant_id = identifier(payload.get('id'), 'merchant_id')
        if action not in ('view', 'rotate'):
            raise ServiceError('NOT_FOUND', '接口不存在。', 404)
        reason = self.reason(payload) if action == 'rotate' else None
        with self.connection(True) as db:
            row = self.merchant_row(db, merchant_id)
            if row is None:
                raise ServiceError('NOT_FOUND', '商户不存在。', 404)
            secret = row['signing_secret']
            if action == 'rotate':
                self.check_version(payload, row)
                secret = secrets.token_hex(32)
                db.execute('UPDATE merchant_signing_credentials SET secret=?,version=version+1 WHERE merchant_id=?', (secret, merchant_id))
                db.execute('UPDATE merchants SET api_secret=?,wallet_secret=?,key_version=key_version+1,version=version+1,updated_at=? WHERE id=?', (secret, secret, int(time.time()), merchant_id))
            result = self.merchant_value(self.merchant_row(db, merchant_id))
            self.audit(db, actor, 'merchant.signing.' + action, merchant_id,
                       details={'reason': reason, 'fingerprint': result['merchant_key_fingerprint']})
        return {'merchant': result, 'keys': {'merchant_secret': secret}}

    @staticmethod
    def reason(payload):
        reason = payload.get('reason', '')
        if not isinstance(reason, str) or not 4 <= len(reason.strip()) <= 300:
            raise ServiceError('REASON_REQUIRED', '请输入 4–300 个字符的操作原因。')
        return reason.strip()

    def user_value(self, row, db=None):
        if db is None:
            with self.connection() as connection:
                return self.user_value(row, connection)
        value = {key: (bool(row[key]) if key == 'enabled' else row[key])
                 for key in ('id', 'username', 'role', 'enabled', 'created_at', 'merchant_id')}
        merchant = db.execute('SELECT name FROM merchants WHERE login_user_id=?', (row['id'],)).fetchone()
        return {**value, 'primary': bool(merchant), 'login_name': merchant['name'] if merchant else row['username']}

    def create_user(self, actor, name, role, password=None, merchant_id=None, scope=None):
        name = username(name)
        if role not in PERMISSIONS:
            raise ServiceError('ROLE_INVALID', '管理员角色无效。')
        password = password or secrets.token_urlsafe(24)
        hashed = password_hash(password)
        with self.connection(True) as db:
            self.validate_user_scope(db, role, merchant_id, scope)
            if role.startswith('merchant_') and db.execute('SELECT 1 FROM merchants WHERE lower(name)=lower(?)', (name,)).fetchone():
                raise ServiceError('USER_EXISTS', '团队账号不能与商户登录名称相同。', 409)
            try:
                db.execute('INSERT INTO admin_users(id,username,password_hash,role,enabled,auth_version,created_at,merchant_id) VALUES (?,?,?,?,?,?,?,?)',
                           (secrets.token_hex(16), name, hashed, role, 1, 1, int(time.time()), merchant_id))
            except sqlite3.IntegrityError:
                raise ServiceError('USER_EXISTS', '用户名已存在。', 409) from None
            if role == 'merchant_admin':
                db.execute('UPDATE merchants SET login_user_id=(SELECT id FROM admin_users WHERE username=?) WHERE id=? AND login_user_id IS NULL', (name, merchant_id))
            self.audit(db, actor, 'user.create', name, details={'role': role})
            result = self.user_value(db.execute('SELECT * FROM admin_users WHERE username=?', (name,)).fetchone(), db)
        return {'user': result, 'temporary_password': password}

    @staticmethod
    def validate_user_scope(db, role, merchant_id, scope=None):
        if role not in PERMISSIONS or bool(merchant_id) != role.startswith('merchant_'):
            raise ServiceError('ROLE_INVALID', '商户角色必须绑定商户，平台角色不能绑定商户。')
        if scope and (merchant_id != scope or not role.startswith('merchant_')):
            raise ServiceError('FORBIDDEN', '只能管理本商户的团队账号。', 403)
        if merchant_id and not db.execute('SELECT 1 FROM merchants WHERE id=?', (merchant_id,)).fetchone():
            raise ServiceError('NOT_FOUND', '商户不存在。', 404)

    def users(self, merchant_id=None):
        with self.connection() as db:
            return [self.user_value(row, db) for row in db.execute('SELECT * FROM admin_users' + (' WHERE merchant_id=?' if merchant_id else '')
                    + ' ORDER BY created_at,username', (merchant_id,) if merchant_id else ())]

    def login(self, name, password, remote, merchant_login=False):
        # Do not echo the supplied username/password in responses or logs.
        safe_name = name.lower() if isinstance(name, str) and 1 <= len(name) <= 80 else ''
        bucket = hashlib.sha256((remote + ':' + safe_name).encode()).hexdigest()
        now = int(time.time())
        with self.connection(True) as db:
            throttle = db.execute('SELECT * FROM admin_login_limits WHERE bucket=?', (bucket,)).fetchone()
            if throttle and throttle['failures'] >= 5 and throttle['until_at'] > now:
                raise ServiceError('LOGIN_THROTTLED', '尝试次数过多，请稍后再试。', 429)
            user = None if merchant_login else db.execute("SELECT * FROM admin_users WHERE username=? AND role NOT LIKE 'merchant_%'", (safe_name,)).fetchone()
            if user is None:
                user = db.execute('SELECT u.* FROM merchants m JOIN admin_users u ON m.login_user_id=u.id WHERE lower(m.name)=lower(?)', (name if safe_name else '',)).fetchone()
                if user is None:
                    user = db.execute("SELECT u.* FROM admin_users u JOIN merchants m ON m.id=u.merchant_id WHERE u.username=? AND u.id<>COALESCE(m.login_user_id,'') AND u.role LIKE 'merchant_%'", (safe_name,)).fetchone()
            valid = password_matches(password, user['password_hash'] if user else self.dummy_hash)
            if user and user['role'].startswith('merchant_') and not user['merchant_id']:
                valid = False
            if not user or not user['enabled'] or not valid:
                failures = throttle['failures'] + 1 if throttle and throttle['until_at'] > now else 1
                db.execute('INSERT OR REPLACE INTO admin_login_limits VALUES (?,?,?)', (bucket, failures, now + 900))
                self.audit(db, safe_name or 'anonymous', 'auth.login', '', 'denied')
                rejection = True
            else:
                db.execute('DELETE FROM admin_login_limits WHERE bucket=?', (bucket,))
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db.execute('DELETE FROM admin_sessions WHERE expires_at<=? OR last_seen<=?', (now, now - 1800))
                db.execute('INSERT INTO admin_sessions VALUES (?,?,?,?,?,?)',
                           (hashlib.sha256(token.encode()).hexdigest(), user['id'], user['auth_version'], csrf, now + 28800, now))
                self.audit(db, user['username'], 'auth.login', '', details={'remote': remote})
                result = {'user': self.user_value(user, db), 'permissions': PERMISSIONS[user['role']], 'csrf_token': csrf}
                rejection = False
        if rejection:
            raise ServiceError('LOGIN_INVALID', '用户名或密码不正确，或账户已停用。', 401)
        return token, result

    def session(self, token, permission=None, csrf=None):
        if not isinstance(token, str) or not 1 <= len(token) <= 128:
            raise ServiceError('LOGIN_REQUIRED', '请先登录管理后台。', 401)
        now = int(time.time())
        hashed = hashlib.sha256(token.encode()).hexdigest()
        with self.connection(True) as db:
            row = db.execute('''SELECT u.*,s.csrf_token,s.expires_at,s.last_seen,s.auth_version AS session_version
                FROM admin_sessions s JOIN admin_users u ON s.user_id=u.id WHERE s.token_hash=?''', (hashed,)).fetchone()
            if (not row or not row['enabled'] or row['expires_at'] <= now or row['last_seen'] <= now - 1800
                    or row['auth_version'] != row['session_version']
                    or (row['role'].startswith('merchant_') and not row['merchant_id'])):
                raise ServiceError('LOGIN_REQUIRED', '登录已过期，请重新登录。', 401)
            if csrf is not None and (not isinstance(csrf, str) or not hmac.compare_digest(csrf, row['csrf_token'])):
                raise ServiceError('CSRF_INVALID', '请求校验失败，请刷新页面。', 403)
            if permission and permission not in PERMISSIONS[row['role']]:
                self.audit(db, row['username'], 'permission.denied', permission, 'denied')
                denied = True
            else:
                db.execute('UPDATE admin_sessions SET last_seen=? WHERE token_hash=?', (now, hashed))
                denied = False
                result = {'user': self.user_value(row, db), 'permissions': PERMISSIONS[row['role']], 'csrf_token': row['csrf_token']}
        if denied:
            raise ServiceError('FORBIDDEN', '当前角色没有此操作权限。', 403)
        return result

    def logout(self, token, actor):
        with self.connection(True) as db:
            db.execute('DELETE FROM admin_sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
            self.audit(db, actor, 'auth.logout', '')

    def change_password(self, actor, current, new):
        hashed = password_hash(new)
        with self.connection(True) as db:
            row = db.execute('SELECT * FROM admin_users WHERE username=?', (actor,)).fetchone()
            if not row or not password_matches(current, row['password_hash']):
                raise ServiceError('PASSWORD_INVALID', '当前密码不正确。', 403)
            db.execute('UPDATE admin_users SET password_hash=?,auth_version=auth_version+1 WHERE id=?', (hashed, row['id']))
            self.audit(db, actor, 'user.password.change', actor)

    def update_user(self, actor, payload, reset=False, scope=None):
        name = username(payload.get('username'))
        with self.connection(True) as db:
            row = db.execute('SELECT * FROM admin_users WHERE username=?', (name,)).fetchone()
            if row is None:
                raise ServiceError('NOT_FOUND', '用户不存在。', 404)
            if scope and row['merchant_id'] != scope:
                raise ServiceError('NOT_FOUND', '用户不存在。', 404)
            if reset:
                password = secrets.token_urlsafe(24)
                db.execute('UPDATE admin_users SET password_hash=?,auth_version=auth_version+1 WHERE id=?',
                           (password_hash(password), row['id']))
                action, details = 'user.password.reset', {}
            else:
                role, enabled = payload.get('role'), payload.get('enabled')
                if role not in PERMISSIONS or type(enabled) is not bool:
                    raise ServiceError('ROLE_INVALID', '请核对角色和账户状态。')
                merchant_id = payload.get('merchant_id', row['merchant_id']) or None
                self.validate_user_scope(db, role, merchant_id, scope)
                if row['role'] == 'merchant_admin' and row['enabled'] and (role != 'merchant_admin' or not enabled or merchant_id != row['merchant_id']):
                    if db.execute("SELECT COUNT(*) FROM admin_users WHERE role='merchant_admin' AND enabled=1 AND merchant_id=?", (row['merchant_id'],)).fetchone()[0] <= 1:
                        raise ServiceError('LAST_ADMIN', '至少保留一名启用的商户管理员。', 409)
                if row['role'] == 'admin' and row['enabled'] and (role != 'admin' or not enabled):
                    if db.execute("SELECT COUNT(*) FROM admin_users WHERE role='admin' AND enabled=1").fetchone()[0] <= 1:
                        raise ServiceError('LAST_ADMIN', '至少保留一名启用的管理员。', 409)
                db.execute('UPDATE admin_users SET role=?,enabled=?,merchant_id=?,auth_version=auth_version+1 WHERE id=?',
                           (role, enabled, merchant_id, row['id']))
                if row['merchant_id'] and (role != 'merchant_admin' or not enabled or merchant_id != row['merchant_id']):
                    db.execute("UPDATE merchants SET login_user_id=(SELECT id FROM admin_users WHERE merchant_id=? AND role='merchant_admin' AND enabled=1 ORDER BY created_at,id LIMIT 1) WHERE id=? AND login_user_id=?", (row['merchant_id'], row['merchant_id'], row['id']))
                action, details = 'user.update', {'role': role, 'enabled': enabled, 'merchant_id': row['merchant_id']}
            self.audit(db, actor, action, name, details=details)
        return {'temporary_password': password} if reset else {'updated': True}

    def audits(self, payload, merchant_id=None):
        count = limit(payload.get('limit', 50))
        before = payload.get('before_seq', 0)
        if type(before) is not int or not 0 <= before <= 9_000_000_000_000_000:
            raise ServiceError('INVALID_ARGUMENT', 'before_seq 无效。')
        clauses, params = [], []
        if merchant_id:
            clauses.append('merchant_id=?')
            params.append(merchant_id)
        for field in ('actor', 'action', 'target'):
            value = payload.get(field, '')
            if not isinstance(value, str) or len(value) > 128:
                raise ServiceError('INVALID_ARGUMENT', '审计筛选参数无效。')
            if value:
                clauses.append(field + '=?')
                params.append(value)
        if before:
            clauses.append('seq<?')
            params.append(before)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with self.connection() as db:
            rows = db.execute('SELECT * FROM admin_audit' + where + ' ORDER BY seq DESC LIMIT ?', (*params, count)).fetchall()
        return [{**{key: row[key] for key in ('seq', 'created_at', 'actor', 'action', 'target', 'outcome')},
                 'details': json.loads(row['details_json'])} for row in rows]


class MerchantDirectory(Mapping):
    """Read fresh records on every access; running services never cache keys/permissions."""
    def __init__(self, store):
        self.store = store

    def __getitem__(self, key):
        value = self.store.merchant(key, private=True)
        if value is None:
            raise KeyError(key)
        return value

    def __iter__(self):
        return iter([row['id'] for row in self.store.merchants()])

    def __len__(self):
        with self.store.connection() as db:
            return db.execute('SELECT COUNT(*) FROM merchants').fetchone()[0]
