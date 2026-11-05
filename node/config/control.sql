
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
