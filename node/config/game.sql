
                CREATE TABLE IF NOT EXISTS merchant_sessions (
                    token_hash TEXT PRIMARY KEY, merchant_id TEXT NOT NULL, player_id TEXT NOT NULL,
                    game_id TEXT NOT NULL, expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS merchant_states (
                    merchant_id TEXT NOT NULL, player_id TEXT NOT NULL, game_id TEXT NOT NULL,
                    state_json TEXT NOT NULL, PRIMARY KEY(merchant_id,player_id,game_id));
                CREATE TABLE IF NOT EXISTS game_operations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                    merchant_id TEXT NOT NULL, player_id TEXT NOT NULL, game_id TEXT NOT NULL,
                    request_key TEXT NOT NULL, request_json TEXT NOT NULL,
                    status TEXT NOT NULL, candidate_json TEXT NOT NULL, debit_json TEXT,
                    response_json TEXT, error_code TEXT, created_at INTEGER NOT NULL,
                    UNIQUE(merchant_id,player_id,game_id,request_key));
                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_game_operation
                    ON game_operations(merchant_id,player_id,game_id) WHERE status IN ('prepared','debited');


                CREATE TABLE IF NOT EXISTS merchant_players (
                    merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,external_username TEXT NOT NULL,
                    prebet_type TEXT NOT NULL DEFAULT 'NORMAL',
                    PRIMARY KEY(merchant_id,player_id),UNIQUE(merchant_id,external_username));
                CREATE TABLE IF NOT EXISTS prebet_rounds (
                    id TEXT PRIMARY KEY,merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id TEXT NOT NULL,
                    initial_sid TEXT NOT NULL,request_json TEXT NOT NULL,initial_state_json TEXT NOT NULL,
                    bet_json TEXT NOT NULL,prebet_request_json TEXT NOT NULL,policy_json TEXT,plan_json TEXT,
                    created_at INTEGER NOT NULL,error_code TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_prebet_start
                    ON prebet_rounds(merchant_id,player_id,game_id,initial_sid) WHERE error_code IS NULL;


                CREATE TABLE IF NOT EXISTS rtp_models (
                    id TEXT PRIMARY KEY,target_bp INTEGER,model_hash TEXT NOT NULL,report_json TEXT NOT NULL,
                    published INTEGER NOT NULL,created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_policies (
                    scope TEXT NOT NULL,merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id INTEGER NOT NULL,
                    model_id TEXT REFERENCES rtp_models(id),revision INTEGER NOT NULL,actor TEXT NOT NULL,updated_at INTEGER NOT NULL,
                    PRIMARY KEY(scope,merchant_id,player_id,game_id));
                CREATE TABLE IF NOT EXISTS rtp_modes (
                    merchant_id TEXT PRIMARY KEY,mode TEXT NOT NULL,revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_bindings (
                    merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id TEXT NOT NULL,initial_sid TEXT NOT NULL,
                    round_id TEXT,model_id TEXT NOT NULL REFERENCES rtp_models(id),play_mode TEXT NOT NULL,mode TEXT NOT NULL,
                    source TEXT NOT NULL,revision INTEGER NOT NULL,settings_json TEXT NOT NULL,created_at INTEGER NOT NULL,
                    PRIMARY KEY(merchant_id,player_id,game_id,initial_sid));
                CREATE INDEX IF NOT EXISTS rtp_binding_round ON rtp_bindings(merchant_id,player_id,game_id,round_id);
                CREATE TABLE IF NOT EXISTS rtp_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,merchant_id TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,
                    details_json TEXT NOT NULL,created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_jobs (
                    id TEXT PRIMARY KEY,target_bp INTEGER NOT NULL,status TEXT NOT NULL,actor TEXT NOT NULL,
                    progress_json TEXT NOT NULL,result_id TEXT,error TEXT,lease TEXT,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_workers (id TEXT PRIMARY KEY,updated_at INTEGER NOT NULL,processes INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS rtp_accounted_ops (operation_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS rtp_facts (
                    merchant_id TEXT NOT NULL,player_id TEXT NOT NULL,game_id INTEGER NOT NULL,round_id TEXT NOT NULL,
                    play_mode TEXT NOT NULL,mode TEXT NOT NULL,target_bp INTEGER,model_id TEXT,
                    debit_minor TEXT NOT NULL,credit_minor TEXT NOT NULL,closed INTEGER NOT NULL,
                    started_at INTEGER NOT NULL,closed_at INTEGER,voided INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(merchant_id,player_id,game_id,round_id));
                CREATE INDEX IF NOT EXISTS rtp_facts_scope ON rtp_facts(merchant_id,player_id,game_id,closed_at);
