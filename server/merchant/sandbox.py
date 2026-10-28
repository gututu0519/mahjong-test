"""Run the gateway, platform wallet and management UI for local integration."""
import argparse
import json
import logging
import secrets
from pathlib import Path
from urllib.parse import urljoin

from server.games.buffalo_win.engine import BuffaloWin
from .common import encode
from .http import build_gateway, build_platform, post_gateway
from .control import ControlStore, MerchantDirectory
from .deployment import Deployment

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / 'services/gtt-gateway/data/sandbox.json'


def load_config(path):
    path = path.resolve()
    config = json.loads(path.read_bytes())
    deployment = Deployment(config)
    if deployment.production:
        if 'merchants' in config or any(key.startswith('sandbox_') for key in config):
            raise ValueError('Production configuration must not seed sandbox merchants or players.')
        for key in ('merchant_database', 'game_database', 'log_directory', 'bootstrap_directory'):
            if not isinstance(config.get(key), str) or not Path(config[key]).is_absolute():
                raise ValueError('Production requires an absolute ' + key + ' path.')
        config['gateway_origin'] = deployment.origins['api']
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
    config = {'gateway_origin': 'http://127.0.0.1:8110', 'sandbox_merchant': 'GTT000001',
              'sandbox_player': 'demo-player', 'sandbox_external_username': 'demo-platform-player', 'sandbox_balance_minor': 200000,
              'merchants': {'GTT000001': {'name': 'Demo Merchant', 'enabled': True, 'merchant_secret': secrets.token_hex(32), 'wallet_url': 'http://127.0.0.1:8111',
                  'currency': 'USD', 'minor_unit': 100, 'games': ['buffalo-win'],
                  'pre_payout': {'enabled': True, 'url': 'http://127.0.0.1:8111/api/v1/callbacks/gtt/preBetDecision'}}}}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print('Created private merchant configuration:', path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'gateway', 'platform', 'launch', 'transactions', 'retry', 'admin-init', 'admin', 'migrate-identifiers'))
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--port', type=int)
    parser.add_argument('--language', choices=('en', 'zh'), default='en')
    parser.add_argument('--operation-id')
    parser.add_argument('--username', default='admin')
    args = parser.parse_args()
    if args.action == 'init':
        return initialize(args.config)
    if args.action == 'migrate-identifiers':
        from .migrate_identifiers import migrate_identifiers
        raw = json.loads(args.config.read_bytes())
        if Deployment(raw).production:
            parser.error('Migrate local identifiers before exporting data for production.')
        database = Path(raw.get('merchant_database', args.config.parent / 'merchants.sqlite3'))
        if not database.is_absolute():
            database = args.config.parent / database
        print(encode(migrate_identifiers(database, ROOT / 'services/gtt-gateway/data/gtt.sqlite3',
                     ROOT / 'services/gtt-mock-platform/data/platform.sqlite3', args.config,
                     [args.config.parent / 'merchant-demo-bootstrap.json'])))
        return
    config, control = load_config(args.config)
    deployment = Deployment(config)
    if args.action == 'admin-init':
        if control.users():
            parser.error('Administrator accounts already exist; use the administration UI.')
        credentials = Path(config.get('bootstrap_directory', args.config.parent)) / 'admin-bootstrap.json'
        credentials.parent.mkdir(parents=True, exist_ok=True)
        if credentials.exists():
            parser.error('Bootstrap credentials already exist; preserving the private file.')
        result = control.create_user('system', args.username, 'admin')
        with credentials.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump({'username': result['user']['username'], 'password': result['temporary_password'],
                       'url': deployment.origins['admin'] + '/' if deployment.production else 'http://127.0.0.1:8112/'}, stream, indent=2)
            stream.write('\n')
        print('Administrator created. Initial credentials saved privately:', credentials)
        return
    if args.action in ('launch', 'transactions', 'retry'):
        if Deployment(config).production:
            parser.error('These commands use the local simulator; use the signed merchant API in production.')
        if args.action == 'launch':
            data = post_gateway(config, '/gtt/v1/games/launch', {'player_id': config['sandbox_player'],
                                'game_id': 1, 'language': args.language,
                                **({'external_username': config['sandbox_external_username']} if config.get('sandbox_external_username') else {})})
            print(urljoin(config['gateway_origin'], data['launch_url']))
        elif args.action == 'transactions':
            print(encode(post_gateway(config, '/gtt/v1/transactions/list', {'limit': 100})))
        else:
            if not args.operation_id:
                parser.error('retry requires --operation-id')
            print(encode(post_gateway(config, '/gtt/v1/transactions/retry', {'operation_id': args.operation_id})))
        return
    service_id = {'gateway': 'gtt-gateway', 'platform': 'gtt-mock-platform', 'admin': 'gtt-admin'}[args.action]
    directory = ROOT / 'services' / service_id
    logs = Path(config.get('log_directory', directory / 'logs'))
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(logs / (service_id + '.log' if deployment.production else 'service.log'), encoding='utf-8'), logging.StreamHandler()])
    if args.action == 'gateway':
        game = BuffaloWin(directory / 'config/buffalo-win.json')
        http = build_gateway(args.port or 8110, Path(config.get('game_database', directory / 'data/gtt.sqlite3')), config, game)
    elif args.action == 'platform':
        if Deployment(config).production:
            parser.error('The mock wallet is not enabled in production.')
        http = build_platform(args.port or 8111, directory / 'data/platform.sqlite3', config)
    else:
        from .admin import build_admin
        from .provider import MerchantService
        game = BuffaloWin(ROOT / 'services/gtt-gateway/config/buffalo-win.json')
        provider = MerchantService(Path(config.get('game_database', ROOT / 'services/gtt-gateway/data/gtt.sqlite3')), config['merchants'], game)
        http = build_admin(args.port or 8112, control, provider, gateway_origin=config.get('gateway_origin'), config=config)
    with http:
        logging.info('%s listening on http://127.0.0.1:%s', service_id, http.server_port)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
