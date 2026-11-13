BEGIN TRANSACTION;
CREATE TABLE admin_audit (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER NOT NULL,
                    actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL,
                    outcome TEXT NOT NULL, details_json TEXT NOT NULL, merchant_id TEXT);
INSERT INTO "admin_audit" VALUES(1,1793860058,'fixture','user.create','admin','success','{"role":"admin"}',NULL);
INSERT INTO "admin_audit" VALUES(2,1793860059,'fixture','merchant.create','GTT000001','success','{"after":{"created_at":1793860058,"currency":"USD","enabled":true,"games":[1],"id":"GTT000001","key_version":1,"login_username":"owner_f8eb86a2a61715c64dc54613d431d6d9","merchant_key_fingerprint":"8ed4de25e224","merchant_key_version":1,"minor_unit":100,"name":"legacy-merchant","pre_payout":{"enabled":false,"url":""},"signing_mode":"unified","updated_at":1793860058,"version":1,"wallet_url":"http://127.0.0.1:1"},"before":null}','GTT000001');
CREATE TABLE admin_login_limits (
                    bucket TEXT PRIMARY KEY, failures INTEGER NOT NULL, until_at INTEGER NOT NULL);
CREATE TABLE admin_sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES admin_users(id),
                    auth_version INTEGER NOT NULL, csrf_token TEXT NOT NULL,
                    expires_at INTEGER NOT NULL, last_seen INTEGER NOT NULL);
CREATE TABLE admin_users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                    role TEXT NOT NULL, enabled INTEGER NOT NULL, auth_version INTEGER NOT NULL,
                    created_at INTEGER NOT NULL, merchant_id TEXT REFERENCES merchants(id));
INSERT INTO "admin_users" VALUES('11805b2076a3b6d25a6c584bbd67c707','admin','pbkdf2_sha256$600000$634eb5d8413c36aefbafe3b276435364$52fa4e3a4964ac223287d38e11cd1f8e115daffd0ee558b0da4348e29a39dc82','admin',1,1,1793860058,NULL);
INSERT INTO "admin_users" VALUES('f8eb86a2a61715c64dc54613d431d6d9','owner_f8eb86a2a61715c64dc54613d431d6d9','pbkdf2_sha256$600000$402a1f5ce7ecc800f34dea3d74deb0f4$1b7d9ccd1b67337a431d27f373cac88435be58a16cb419a5996456713b46ef9c','merchant_admin',1,1,1793860058,'GTT000001');
CREATE TABLE control_counters (name TEXT PRIMARY KEY,value INTEGER NOT NULL);
INSERT INTO "control_counters" VALUES('merchant',1);
CREATE TABLE merchant_prebet_settings (
                    merchant_id TEXT PRIMARY KEY REFERENCES merchants(id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL,url TEXT NOT NULL,operator_token TEXT NOT NULL,secret_key TEXT NOT NULL);
INSERT INTO "merchant_prebet_settings" VALUES('GTT000001',0,'','','');
CREATE TABLE merchant_signing_credentials (
                    merchant_id TEXT PRIMARY KEY REFERENCES merchants(id) ON DELETE CASCADE,
                    secret TEXT NOT NULL,mode TEXT NOT NULL,version INTEGER NOT NULL,ready INTEGER NOT NULL);
INSERT INTO "merchant_signing_credentials" VALUES('GTT000001','d7c875feb9ace943e9abadbe62a1aa59ef665eb56ed567312447468d225d8637','unified',1,0);
CREATE TABLE merchants (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL,
                    wallet_url TEXT NOT NULL, currency TEXT NOT NULL, minor_unit INTEGER NOT NULL,
                    games_json TEXT NOT NULL, api_secret TEXT NOT NULL, wallet_secret TEXT NOT NULL,
                    version INTEGER NOT NULL, key_version INTEGER NOT NULL,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, login_user_id TEXT);
INSERT INTO "merchants" VALUES('GTT000001','legacy-merchant',1,'http://127.0.0.1:1','USD',100,'["buffalo-win"]','d7c875feb9ace943e9abadbe62a1aa59ef665eb56ed567312447468d225d8637','d7c875feb9ace943e9abadbe62a1aa59ef665eb56ed567312447468d225d8637',1,1,1793860058,1793860058,'f8eb86a2a61715c64dc54613d431d6d9');
CREATE TABLE request_nonces (
                merchant_id TEXT NOT NULL, nonce TEXT NOT NULL, expires_at INTEGER NOT NULL,
                PRIMARY KEY(merchant_id,nonce));
CREATE INDEX audit_merchant_seq ON admin_audit(merchant_id,seq);
CREATE UNIQUE INDEX merchant_login_name ON merchants(lower(name));
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('admin_audit',2);
COMMIT;