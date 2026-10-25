import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from server.core.contracts import ServiceError


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', value):
        raise ServiceError('INVALID_ARGUMENT', name + ' must use 1..128 ASCII letters, digits, or _ . : -')
    return value


def amount(value):
    if type(value) is not int or not 0 <= value <= 9_000_000_000_000_000:
        raise ServiceError('INVALID_ARGUMENT', 'amount_minor must be a nonnegative integer within the balance limit.')
    return value


def limit(value=20):
    if type(value) is not int or not 1 <= value <= 100:
        raise ServiceError('INVALID_ARGUMENT', 'limit must be an integer from 1 to 100.')
    return value


def signature(secret, method, path, timestamp, nonce, body):
    message = '\n'.join((method.upper(), path, str(timestamp), nonce, hashlib.sha256(body).hexdigest()))
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def signed_headers(merchant_id, secret, path, body, timestamp=None, nonce=None):
    timestamp = str(int(time.time()) if timestamp is None else timestamp)
    nonce = secrets.token_hex(16) if nonce is None else nonce
    return {'Content-Type': 'application/json', 'X-GTT-Merchant': merchant_id,
            'X-GTT-Timestamp': timestamp, 'X-GTT-Nonce': nonce,
            'X-GTT-Signature': signature(secret, 'POST', path, timestamp, nonce, body)}


class Database:
    def __init__(self, path):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS request_nonces (
                merchant_id TEXT NOT NULL, nonce TEXT NOT NULL, expires_at INTEGER NOT NULL,
                PRIMARY KEY(merchant_id,nonce))''')

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, isolation_level=None, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def authenticate(self, headers, path, body, merchants, secret_field, allow_disabled=False):
        merchant_id = headers.get('X-GTT-Merchant', '')
        merchant = merchants.get(merchant_id)
        if not merchant or (not merchant.get('enabled') and not allow_disabled):
            raise ServiceError('AUTH_INVALID', 'Unknown or disabled merchant.', 401)
        timestamp, nonce = headers.get('X-GTT-Timestamp', ''), headers.get('X-GTT-Nonce', '')
        now = int(time.time())
        if (not re.fullmatch(r'[0-9]{10}', timestamp) or abs(now - int(timestamp)) > 300
                or not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', nonce)):
            raise ServiceError('AUTH_INVALID', 'Invalid timestamp or nonce.', 401)
        expected = signature(merchant[secret_field], 'POST', path, timestamp, nonce, body)
        supplied = headers.get('X-GTT-Signature', '')
        if not re.fullmatch(r'[0-9a-f]{64}', supplied) or not hmac.compare_digest(expected, supplied):
            raise ServiceError('AUTH_INVALID', 'Invalid signature.', 401)
        with self.connection(True) as db:
            db.execute('DELETE FROM request_nonces WHERE expires_at<?', (now,))
            try:
                # Keep it until the signed timestamp can no longer pass verification.
                db.execute('INSERT INTO request_nonces VALUES (?,?,?)', (merchant_id, nonce, now + 601))
            except sqlite3.IntegrityError:
                raise ServiceError('AUTH_REPLAY', 'Nonce has already been used.', 409) from None
        return merchant_id, merchant


def read_object(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    result = json.loads(body, object_pairs_hook=pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
    if not isinstance(result, dict):
        raise ValueError('Expected a JSON object')
    return result
