"""Separate deterministic UI checks; never changes the real 8101 service wallet."""
import argparse
import json
from pathlib import Path

from server.services.fortune_rabbit_demo import build_server


def install_last_prize_scenario(game):
    """Use captured layouts as inputs to real rules, never replay responses."""
    root = Path(__file__).resolve().parents[2]
    evidence = json.loads((root / 'clients/fortune-rabbit/fixtures/spin-evidence.json').read_text(encoding='utf-8'))['spins']
    end = next(i for i, row in enumerate(evidence)
               if row['transaction']['st'] == 2 and row['transaction']['nst'] == 1
               and row['transaction'].get('tw', 0) > 0)
    sequence = evidence[end - 7:end + 1]
    original_step = game.step
    planned = sequence[0]['transaction']

    def step(state, bet, seed, sid):
        nonlocal planned
        index = 0 if state['phase'] == 'ready' else state['step']
        planned = sequence[index]['transaction']
        return original_step(state, bet, seed, sid)

    def prizes(rng, board, total_bet):
        return {k: dict(p=v.get('p', 0), m=v['m'], bv=total_bet * v['m'] / 100)
                for k, v in planned.get('cpf', {}).items()}

    game._trigger_feature = lambda rng: True
    game._new_board = lambda rng, feature=False: list(planned['orl'])
    game._prizes = prizes
    game.step = step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18112)
    parser.add_argument('--scenario', choices=['random', 'last-prize'], default='random')
    args = parser.parse_args()
    if not 18000 <= args.port <= 18999:
        parser.error('Acceptance ports must be in 18000..18999')
    database = Path(__file__).resolve().parents[2] / f'diagnostics/rabbit-acceptance-{args.port}.sqlite3'
    database.parent.mkdir(parents=True, exist_ok=True)
    configuration = database.with_suffix('.config.json')
    normal = Path(__file__).resolve().parents[2] / 'services/fortune-rabbit/config/fortune-rabbit.json'
    config = json.loads(normal.read_text(encoding='utf-8'))
    config['feature_probability'] = 1
    configuration.write_text(json.dumps(config), encoding='utf-8')
    with build_server(args.port, database, configuration) as http:
        if args.scenario == 'last-prize':
            install_last_prize_scenario(http.pg.game)
        http.service_id = 'fortune-rabbit-acceptance'
        print(f'Acceptance only: http://127.0.0.1:{args.port}/?mock=1&l=en', flush=True)
        http.serve_forever()


if __name__ == '__main__':
    main()
