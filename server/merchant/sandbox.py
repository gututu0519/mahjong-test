"""Run the gateway, platform wallet and management UI for local integration."""
import argparse
import json
import logging
import secrets
from pathlib import Path

from server.games.buffalo_win.engine import BuffaloWin
from .common import encode
from .http import build_gateway, build_platform, post_gateway
from .control import ControlStore, MerchantDirectory

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / 'services/gtt-gateway/data/sandbox.json'


def load_config(path):
    path = path.resolve()
    config = json.loads(path.read_bytes())
    database = Path(config.get('merchant_database', path.parent / 'merchants.sqlite3'))
    if not database.is_absolute():
        database = (path.parent / database).resolve()
    control = ControlStore(database)
    if 'merchants' in config:
        control.migrate(config['merchants'])
        config.pop('merchants')
        config['merchant_database'] = str(database.resolve())
        # Keep the legacy private file recoverable, but never reload its keys.
        backup = path.with_name(path.stem + '.before-admin.json')
        if not backup.exists():
            with backup.open('xb') as stream:
                stream.write(path.read_bytes())
        temporary = path.with_name(path.name + '.' + secrets.token_hex(4) + '.tmp')
        temporary.write_bytes((json.dumps(config, ensure_ascii=False, indent=2) + '\n').encode())
        temporary.replace(path)
    config['merchants'] = MerchantDirectory(control)
    return config, control


def initialize(path):
    if path.exists():
        raise ValueError('Configuration already exists; preserving merchants and keys: ' + str(path))
    config = {'gateway_origin': 'http://127.0.0.1:8110', 'sandbox_merchant': 'demo-platform',
              'sandbox_player': 'demo-player', 'sandbox_balance_minor': 200000,
              'merchants': {'demo-platform': {'enabled': True, 'api_secret': secrets.token_hex(32),
                  'wallet_secret': secrets.token_hex(32), 'wallet_url': 'http://127.0.0.1:8111',
                  'currency': 'DEMO', 'minor_unit': 100, 'games': ['buffalo-win']}}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print('Created private merchant configuration:', path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'gateway', 'platform', 'launch', 'transactions', 'retry', 'admin-init', 'admin'))
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--port', type=int)
    parser.add_argument('--language', choices=('en', 'zh'), default='en')
    parser.add_argument('--operation-id')
    parser.add_argument('--username', default='admin')
    args = parser.parse_args()
    if args.action == 'init':
        return initialize(args.config)
    config, control = load_config(args.config)
    if args.action == 'admin-init':
        if control.users():
            parser.error('Administrator accounts already exist; use the administration UI.')
        credentials = args.config.parent / 'admin-bootstrap.json'
        if credentials.exists():
            parser.error('Bootstrap credentials already exist; preserving the private file.')
        result = control.create_user('system', args.username, 'admin')
        with credentials.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump({'username': result['user']['username'], 'password': result['temporary_password'],
                       'url': 'http://127.0.0.1:8112/'}, stream, indent=2)
            stream.write('\n')
        print('Administrator created. Initial credentials saved privately:', credentials)
        return
    if args.action in ('launch', 'transactions', 'retry'):
        if args.action == 'launch':
            data = post_gateway(config, '/gtt/v1/games/launch', {'player_id': config['sandbox_player'],
                                'game_id': 'buffalo-win', 'language': args.language})
            print(config['gateway_origin'] + data['launch_url'])
        elif args.action == 'transactions':
            print(encode(post_gateway(config, '/gtt/v1/transactions/list', {'limit': 100})))
        else:
            if not args.operation_id:
                parser.error('retry requires --operation-id')
            print(encode(post_gateway(config, '/gtt/v1/transactions/retry', {'operation_id': args.operation_id})))
        return
    service_id = {'gateway': 'gtt-gateway', 'platform': 'gtt-mock-platform', 'admin': 'gtt-admin'}[args.action]
    directory = ROOT / 'services' / service_id
    logs = directory / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(logs / 'service.log', encoding='utf-8'), logging.StreamHandler()])
    if args.action == 'gateway':
        game = BuffaloWin(directory / 'config/buffalo-win.json')
        http = build_gateway(args.port or 8110, directory / 'data/gtt.sqlite3', config, game)
    elif args.action == 'platform':
        http = build_platform(args.port or 8111, directory / 'data/platform.sqlite3', config)
    else:
        from .admin import build_admin
        from .provider import MerchantService
        game = BuffaloWin(ROOT / 'services/gtt-gateway/config/buffalo-win.json')
        provider = MerchantService(ROOT / 'services/gtt-gateway/data/gtt.sqlite3', config['merchants'], game)
        http = build_admin(args.port or 8112, control, provider)
    with http:
        logging.info('%s listening on http://127.0.0.1:%s', service_id, http.server_port)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
