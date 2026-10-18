"""Deterministic UI acceptance service, isolated from normal port 8100 and its data."""
import argparse
import json
import logging
from pathlib import Path
from server.services.wild_bandito_demo import build_server


def losing_board():
    return [s for s in (2, 3, 4, 5, 6) for _ in range(5)]


def install_scenario(game, scenario='basic', scatters=3):
    """Use persisted round state, so reloading never resets the scenario sequence."""
    original_step = game.step
    planned = losing_board()

    def step(state, bet, seed, sid):
        nonlocal planned
        planned = losing_board()
        free = state.get('free')
        if state['phase'] == 'ready' and state['sid'] == '0':
            for c in range(scatters):
                planned[c * 5 + 1] = 1
        elif state['phase'] == 'free_start':
            retrigger = (scenario == 'retrigger' and free['remaining'] == free['total'] - 1
                         and free['total'] == 12 + (scatters - 3) * 2)
            last_retrigger = scenario == 'last-retrigger' and free['remaining'] == 1 and free['total'] == 12 + (scatters - 3) * 2
            if retrigger or last_retrigger:
                for p in (1, 6, 11):
                    planned[p] = 1
            elif scenario != 'no-win' and (free['remaining'] == free['total'] or free['remaining'] == 1):
                planned[6] = planned[11] = 2
        return original_step(state, bet, seed, sid)

    game._new_board = lambda rng: list(planned)
    game._draw_column = lambda rng, count, has_scatter=False: [10] * count
    game.step = step


def build_acceptance(port, database, scenario='basic', scatters=3):
    config = Path(database).with_suffix('.config.json')
    normal = Path('services/wild-bandito/config/wild-bandito.json')
    data = json.loads(normal.read_text(encoding='utf-8'))
    data['gold_probability'] = 0  # Mandatory free middle-reel gold still applies.
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(data), encoding='utf-8')
    http = build_server(port, database, config)
    install_scenario(http.pg.game, scenario, scatters)
    return http


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18110)
    parser.add_argument('--scenario', choices=['basic', 'no-win', 'retrigger', 'last-retrigger'], default='basic')
    parser.add_argument('--scatters', type=int, choices=[3, 4, 5], default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    database = Path('diagnostics') / f'wild-acceptance-{args.port}.sqlite3'
    http = build_acceptance(args.port, database, args.scenario, args.scatters)
    with http:
        http.serve_forever()


if __name__ == '__main__':
    main()
