"""Database-backed merchant configuration, administrator sessions and audit trail."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from collections.abc import Mapping
from urllib.parse import urlsplit

from server.core.contracts import ServiceError
from .common import Database, encode, identifier, limit

PERMISSIONS = {
    'admin': ('merchants.read', 'merchants.write', 'keys.rotate', 'games.read', 'transactions.read',
              'transactions.retry', 'audit.read', 'users.manage'),
    'operator': ('merchants.read', 'games.read', 'transactions.read', 'transactions.retry', 'audit.read'),
    'viewer': ('merchants.read', 'games.read', 'transactions.read', 'audit.read'),
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
            ''')
        # Used for a comparable password-check cost for unknown usernames.
        self.dummy_hash = password_hash('not-a-real-admin-password', '0' * 32)

    @staticmethod
    def audit(db, actor, action, target, outcome='success', details=None):
        db.execute('INSERT INTO admin_audit(created_at,actor,action,target,outcome,details_json) VALUES (?,?,?,?,?,?)',
                   (int(time.time()), actor, action, target, outcome, encode(details or {})))

    @staticmethod
    def merchant_value(row, private=False):
        if row is None:
            return None
        value = {key: row[key] for key in ('id', 'name', 'wallet_url', 'currency', 'minor_unit',
                                          'version', 'key_version', 'created_at', 'updated_at')}
        value.update(enabled=bool(row['enabled']), games=json.loads(row['games_json']))
        if private:
            value.update(api_secret=row['api_secret'], wallet_secret=row['wallet_secret'])
        else:
            value['api_key_fingerprint'] = hashlib.sha256(row['api_secret'].encode()).hexdigest()[:12]
            value['wallet_key_fingerprint'] = hashlib.sha256(row['wallet_secret'].encode()).hexdigest()[:12]
        return value

    def migrate(self, merchants):
        with self.connection(True) as db:
            for merchant_id, merchant in merchants.items():
                identifier(merchant_id, 'merchant_id')
                now = int(time.time())
                result = db.execute('INSERT OR IGNORE INTO merchants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (merchant_id, merchant.get('name', merchant_id), bool(merchant['enabled']),
                     wallet_origin(merchant['wallet_url']), merchant['currency'], merchant['minor_unit'],
                     encode(merchant['games']), merchant['api_secret'], merchant['wallet_secret'], 1, 1, now, now))
                if result.rowcount:
                    self.audit(db, 'system', 'merchant.migrate', merchant_id)

    def merchants(self):
        with self.connection() as db:
            return [self.merchant_value(row) for row in db.execute('SELECT * FROM merchants ORDER BY created_at,id')]

    def merchant(self, merchant_id, private=False):
        with self.connection() as db:
            return self.merchant_value(db.execute('SELECT * FROM merchants WHERE id=?', (merchant_id,)).fetchone(), private)

    def save_merchant(self, actor, payload, games, create=False):
        merchant_id = identifier(payload.get('id'), 'merchant_id')
        name = payload.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
            raise ServiceError('NAME_INVALID', '商户名称须为 1–80 个可见字符。')
        enabled = payload.get('enabled')
        selected = payload.get('games')
        if (type(enabled) is not bool or not isinstance(selected, list)
                or any(not isinstance(value, str) or value not in games for value in selected)
                or len(selected) != len(set(selected))):
            raise ServiceError('MERCHANT_INVALID', '请核对商户状态与游戏授权。')
        origin = wallet_origin(payload.get('wallet_url'))
        now = int(time.time())
        keys = None
        with self.connection(True) as db:
            old = db.execute('SELECT * FROM merchants WHERE id=?', (merchant_id,)).fetchone()
            if create:
                if old:
                    raise ServiceError('MERCHANT_EXISTS', '商户号已存在。', 409)
                currency = payload.get('currency', 'DEMO')
                if not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3,8}', currency):
                    raise ServiceError('CURRENCY_INVALID', '币种须为 3–8 位大写字母。')
                keys = {'api_secret': secrets.token_hex(32), 'wallet_secret': secrets.token_hex(32)}
                db.execute('INSERT INTO merchants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (merchant_id, name.strip(), enabled, origin, currency, 100, encode(selected),
                     keys['api_secret'], keys['wallet_secret'], 1, 1, now, now))
            else:
                if old is None:
                    raise ServiceError('NOT_FOUND', '商户不存在。', 404)
                self.check_version(payload, old)
                if payload.get('currency', old['currency']) != old['currency']:
                    raise ServiceError('CURRENCY_IMMUTABLE', '已有商户的币种不可变更。')
                db.execute('UPDATE merchants SET name=?,enabled=?,wallet_url=?,games_json=?,version=version+1,updated_at=? WHERE id=?',
                           (name.strip(), enabled, origin, encode(selected), now, merchant_id))
            new = db.execute('SELECT * FROM merchants WHERE id=?', (merchant_id,)).fetchone()
            result = self.merchant_value(new)
            self.audit(db, actor, 'merchant.create' if create else 'merchant.update', merchant_id,
                       details={'before': self.merchant_value(old), 'after': result})
        return {'merchant': result, **({'keys': keys} if keys else {})}

    @staticmethod
    def check_version(payload, row):
        if type(payload.get('version')) is not int or payload['version'] != row['version']:
            raise ServiceError('VERSION_CONFLICT', '配置已被修改，请刷新后重试。', 409)

    def rotate_keys(self, actor, payload):
        merchant_id = identifier(payload.get('id'), 'merchant_id')
        reason = self.reason(payload)
        keys = {'api_secret': secrets.token_hex(32), 'wallet_secret': secrets.token_hex(32)}
        with self.connection(True) as db:
            row = db.execute('SELECT * FROM merchants WHERE id=?', (merchant_id,)).fetchone()
            if row is None:
                raise ServiceError('NOT_FOUND', '商户不存在。', 404)
            self.check_version(payload, row)
            db.execute('UPDATE merchants SET api_secret=?,wallet_secret=?,version=version+1,key_version=key_version+1,updated_at=? WHERE id=?',
                       (keys['api_secret'], keys['wallet_secret'], int(time.time()), merchant_id))
            self.audit(db, actor, 'merchant.keys.rotate', merchant_id,
                       details={'reason': reason, 'key_version': row['key_version'] + 1})
            result = self.merchant_value(db.execute('SELECT * FROM merchants WHERE id=?', (merchant_id,)).fetchone())
        return {'merchant': result, 'keys': keys}

    @staticmethod
    def reason(payload):
        reason = payload.get('reason', '')
        if not isinstance(reason, str) or not 4 <= len(reason.strip()) <= 300:
            raise ServiceError('REASON_REQUIRED', '请输入 4–300 个字符的操作原因。')
        return reason.strip()

    @staticmethod
    def user_value(row):
        return {key: (bool(row[key]) if key == 'enabled' else row[key])
                for key in ('id', 'username', 'role', 'enabled', 'created_at')}

    def create_user(self, actor, name, role, password=None):
        name = username(name)
        if role not in PERMISSIONS:
            raise ServiceError('ROLE_INVALID', '管理员角色无效。')
        password = password or secrets.token_urlsafe(24)
        hashed = password_hash(password)
        with self.connection(True) as db:
            try:
                db.execute('INSERT INTO admin_users VALUES (?,?,?,?,?,?,?)',
                           (secrets.token_hex(16), name, hashed, role, 1, 1, int(time.time())))
            except sqlite3.IntegrityError:
                raise ServiceError('USER_EXISTS', '用户名已存在。', 409) from None
            self.audit(db, actor, 'user.create', name, details={'role': role})
            result = self.user_value(db.execute('SELECT * FROM admin_users WHERE username=?', (name,)).fetchone())
        return {'user': result, 'temporary_password': password}

    def users(self):
        with self.connection() as db:
            return [self.user_value(row) for row in db.execute('SELECT * FROM admin_users ORDER BY created_at,username')]

    def login(self, name, password, remote):
        # Do not echo the supplied username/password in responses or logs.
        safe_name = name.lower() if isinstance(name, str) and len(name) <= 40 else ''
        bucket = hashlib.sha256((remote + ':' + safe_name).encode()).hexdigest()
        now = int(time.time())
        with self.connection(True) as db:
            throttle = db.execute('SELECT * FROM admin_login_limits WHERE bucket=?', (bucket,)).fetchone()
            if throttle and throttle['failures'] >= 5 and throttle['until_at'] > now:
                raise ServiceError('LOGIN_THROTTLED', '尝试次数过多，请稍后再试。', 429)
            user = db.execute('SELECT * FROM admin_users WHERE username=?', (safe_name,)).fetchone()
            valid = password_matches(password, user['password_hash'] if user else self.dummy_hash)
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
                result = {'user': self.user_value(user), 'permissions': PERMISSIONS[user['role']], 'csrf_token': csrf}
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
                    or row['auth_version'] != row['session_version']):
                raise ServiceError('LOGIN_REQUIRED', '登录已过期，请重新登录。', 401)
            if csrf is not None and (not isinstance(csrf, str) or not hmac.compare_digest(csrf, row['csrf_token'])):
                raise ServiceError('CSRF_INVALID', '请求校验失败，请刷新页面。', 403)
            if permission and permission not in PERMISSIONS[row['role']]:
                self.audit(db, row['username'], 'permission.denied', permission, 'denied')
                denied = True
            else:
                db.execute('UPDATE admin_sessions SET last_seen=? WHERE token_hash=?', (now, hashed))
                denied = False
                result = {'user': self.user_value(row), 'permissions': PERMISSIONS[row['role']], 'csrf_token': row['csrf_token']}
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

    def update_user(self, actor, payload, reset=False):
        name = username(payload.get('username'))
        with self.connection(True) as db:
            row = db.execute('SELECT * FROM admin_users WHERE username=?', (name,)).fetchone()
            if row is None:
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
                if row['role'] == 'admin' and row['enabled'] and (role != 'admin' or not enabled):
                    if db.execute("SELECT COUNT(*) FROM admin_users WHERE role='admin' AND enabled=1").fetchone()[0] <= 1:
                        raise ServiceError('LAST_ADMIN', '至少保留一名启用的管理员。', 409)
                db.execute('UPDATE admin_users SET role=?,enabled=?,auth_version=auth_version+1 WHERE id=?',
                           (role, enabled, row['id']))
                action, details = 'user.update', {'role': role, 'enabled': enabled}
            self.audit(db, actor, action, name, details=details)
        return {'temporary_password': password} if reset else {'updated': True}

    def audits(self, payload):
        count = limit(payload.get('limit', 50))
        before = payload.get('before_seq', 0)
        if type(before) is not int or not 0 <= before <= 9_000_000_000_000_000:
            raise ServiceError('INVALID_ARGUMENT', 'before_seq 无效。')
        clauses, params = [], []
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
