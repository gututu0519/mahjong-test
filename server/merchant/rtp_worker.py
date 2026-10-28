"""Durable offline calibration queue; never performs wallet/game operations."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time

from .provider import MerchantService
from .rtp_calibration import calibrate
from .sandbox import load_config
from server.games.buffalo_win.engine import BuffaloWin


def run_once(store, workers=4):
    now, lease = int(time.time()), secrets.token_hex(16)
    with store.write() as db:
        db.execute('INSERT INTO rtp_workers VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,processes=excluded.processes',
                   (str(os.getpid()), now, workers))
        db.execute("UPDATE rtp_jobs SET status='queued',lease=NULL WHERE status='running' AND updated_at<?", (now - 600,))
        row = db.execute("SELECT * FROM rtp_jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
        if row is None:
            return False
        job = dict(row)
        db.execute("UPDATE rtp_jobs SET status='running',lease=?,updated_at=? WHERE id=?", (lease, now, job['id']))
    def progress(event):
        with store.provider.connection(True) as db:
            db.execute('UPDATE rtp_workers SET updated_at=? WHERE id=?', (int(time.time()), str(os.getpid())))
            changed = db.execute('UPDATE rtp_jobs SET progress_json=?,updated_at=? WHERE id=? AND lease=?',
                                 (json.dumps(event), int(time.time()), job['id'], lease)).rowcount
            if not changed:
                raise RuntimeError('Calibration lease was replaced.')
    try:
        report = calibrate(job['target_bp'], workers, progress)
        model = store.import_model(report, 'system', publish=False)
        with store.write() as db:
            db.execute("UPDATE rtp_jobs SET status='ready',result_id=?,updated_at=? WHERE id=? AND lease=?", (model, int(time.time()), job['id'], lease))
            store.event(db, 'system', 'rtp.calibration.ready', model_id=model, job_id=job['id'])
    except Exception as error:
        with store.provider.connection(True) as db:
            db.execute("UPDATE rtp_jobs SET status='failed',error=?,updated_at=? WHERE id=? AND lease=?", (str(error)[:500], int(time.time()), job['id'], lease))
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    config, _ = load_config(args.config)
    database = config.get('game_database', Path(__file__).resolve().parents[2] / 'services/gtt-gateway/data/gtt.sqlite3')
    game = BuffaloWin(Path(__file__).resolve().parents[2] / 'services/gtt-gateway/config/buffalo-win.json')
    provider = MerchantService(database, config['merchants'], game=game)
    while True:
        worked = run_once(provider.rtp, args.workers)
        if args.once:
            break
        if not worked:
            time.sleep(5)
