"""API-only service: no client files, legacy login or provider protocol imports."""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path
from server.core.service import GameService
from server.games.catalog import create_registry
from server.transport.http import APIHandler

ROOT = Path(__file__).resolve().parents[2]


def build_server(port=8082, database=None, game_ids=None, configs=None):
    if game_ids is None:
        game_ids = ['mahjong-ways2']
    if configs is None:
        configs = {game_id: ROOT / 'services/game-api/config' / (game_id + '.json') for game_id in game_ids}
    registry = create_registry(game_ids, configs)
    service = GameService(database or ROOT / 'services/game-api/data/games.sqlite3', registry)
    http = ThreadingHTTPServer(('127.0.0.1', port), APIHandler)
    http.daemon_threads = True
    http.service = service
    return http


def main():
    parser = argparse.ArgumentParser(description='Independent JSON game API service')
    parser.add_argument('--port', type=int, default=8082)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--games', nargs='+', help='Game IDs from the explicit catalog')
    args = parser.parse_args()
    with build_server(args.port, args.database, args.games) as http:
        print(f'Game API: http://localhost:{http.server_port}/api/v1/games', flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
