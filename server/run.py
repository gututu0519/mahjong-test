"""Start exactly one service from its own directory and configuration."""
import argparse
import json
import logging
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_profile(directory):
    directory = Path(directory).resolve()
    spec = json.loads((directory / 'service.json').read_text(encoding='utf-8'))
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', spec['id']):
        raise ValueError('Invalid service ID')
    if spec['entry'] not in ('mahjong_client', 'buffalo_client', 'json_api', 'olympus_preview', 'olympus_client', 'sweet_bonanza_pop_client', 'big_bass_bonanza_client', 'super_ace_client', 'fortune_gems2_client', 'jokers_fortune_winx_client'):
        raise ValueError('Unknown service entry')
    if type(spec['port']) is not int or not 1 <= spec['port'] <= 65535:
        raise ValueError('Invalid service port')
    games = spec['games']
    if spec['entry'] == 'jokers_fortune_winx_client' and games != ['jokers-fortune-winx']:
        raise ValueError('Joker service only supports its own game')
    if spec['entry'] == 'olympus_preview':
        if games != []:
            raise ValueError('Frontend preview must not load game engines')
        return spec, {}
    if not isinstance(games, list) or not games or len(set(games)) != len(games):
        raise ValueError('Explicit nonempty game selection required')
    if spec['entry'] == 'mahjong_client' and games != ['mahjong-ways2']:
        raise ValueError('Mahjong client service only supports its own game')
    if spec['entry'] == 'buffalo_client' and games != ['buffalo-win']:
        raise ValueError('Buffalo client service only supports its own game')
    if spec['entry'] == 'olympus_client' and games != ['gates-of-olympus']:
        raise ValueError('Olympus client service only supports its own game')
    if spec['entry'] == 'big_bass_bonanza_client' and games != ['big-bass-bonanza']:
        raise ValueError('Big Bass service only supports its own game')
    if spec['entry'] == 'fortune_gems2_client' and games != ['fortune-gems2']:
        raise ValueError('Fortune Gems 2 service only supports its own game')
    configs = {}
    if spec['entry'] == 'super_ace_client' and games != ['super-ace']:
        raise ValueError('Super Ace service only supports its own game')
    if spec['entry'] == 'sweet_bonanza_pop_client' and games != ['sweet-bonanza-pop']:
        raise ValueError('Sweet Bonanza POP service only supports its own game')
    for game_id in games:
        path = (directory / 'config' / (game_id + '.json')).resolve()
        if not path.is_relative_to(directory / 'config') or not path.is_file():
            raise ValueError('Each selected game needs a service-owned configuration')
        configs[game_id] = path
    return spec, configs


def build_from_directory(directory, port=None):
    directory = Path(directory).resolve()
    spec, configs = load_profile(directory)
    database = directory / 'data' / 'games.sqlite3'
    # The directory owns all runtime state; no shared/default database fallback.
    actual_port = spec['port'] if port is None else port
    if spec['entry'] == 'olympus_preview':
        from server.services.olympus_preview import build_server
        http = build_server(actual_port)
    elif spec['entry'] == 'jokers_fortune_winx_client':
        from server.services.jokers_fortune_winx_demo import build_server
        http = build_server(actual_port, database, configs['jokers-fortune-winx'])
    elif spec['entry'] == 'fortune_gems2_client':
        from server.services.fortune_gems2_demo import build_server
        http = build_server(actual_port, database, configs['fortune-gems2'])
    elif spec['entry'] == 'super_ace_client':
        from server.services.super_ace_demo import build_server
        http = build_server(actual_port, database, configs['super-ace'])
    elif spec['entry'] == 'big_bass_bonanza_client':
        from server.services.big_bass_bonanza_demo import build_server
        http = build_server(actual_port, database, configs['big-bass-bonanza'])
    elif spec['entry'] == 'sweet_bonanza_pop_client':
        from server.services.sweet_bonanza_pop_demo import build_server
        http = build_server(actual_port, database, configs['sweet-bonanza-pop'])
    elif spec['entry'] == 'olympus_client':
        from server.services.olympus_demo import build_server
        http = build_server(actual_port, database, configs['gates-of-olympus'])
    elif spec['entry'] == 'mahjong_client':
        from server.services.local_demo import build_server
        http = build_server(actual_port, database, configs['mahjong-ways2'])
    elif spec['entry'] == 'buffalo_client':
        from server.services.buffalo_demo import build_server
        http = build_server(actual_port, database, configs['buffalo-win'])
    else:
        from server.services.game_api import build_server
        http = build_server(actual_port, database, spec['games'], configs)
    http.service_id = spec['id']
    return http


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run one isolated local service')
    parser.add_argument('--service-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, help='Optional port override; data stays in this service directory')
    args = parser.parse_args(argv)
    directory = args.service_dir.resolve()
    spec, _ = load_profile(directory)
    logs = directory / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.FileHandler(logs / 'service.log', encoding='utf-8'),
                                  logging.StreamHandler()])
    with build_from_directory(directory, args.port) as http:
        logging.info('Service %s listening on http://localhost:%s; data=%s',
                     spec['id'], http.server_port, directory / 'data')
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            logging.info('Service %s stopped', spec['id'])


if __name__ == '__main__':
    main()
