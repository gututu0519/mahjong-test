"""Explicit game allowlist. Adding games never requires changing wallet code."""
from importlib import import_module
from server.core.contracts import Registry


GAMES = {
    'super-ace': {
        'factory': 'server.games.super_ace:SuperAce',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['ways', 'cascades', 'gold_to_wild', 'wild_copy', 'free_spins', 'free_retrigger', 'buy_bonus'],
    },
    'big-bass-bonanza': {
        'factory': 'server.games.big_bass_bonanza:BigBassBonanza',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['paylines', 'money_collect', 'free_spins', 'free_retrigger'],
    },
    'sweet-bonanza-pop': {
        'factory': 'server.games.sweet_bonanza_pop:SweetBonanzaPop',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['cascades', 'symbol_count', 'multiplier_symbols', 'free_spins', 'free_retrigger'],
    },
    'gates-of-olympus': {
        'factory': 'server.games.gates_of_olympus:GatesOfOlympus',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['cascades', 'symbol_count', 'multiplier_symbols', 'free_spins', 'free_retrigger'],
    },
    'buffalo-win': {
        'factory': 'server.games.buffalo_win:BuffaloWin',
        'category': 'slots',
        'interaction': 'request_steps',
        'features': ['expanding_reels', 'expanded_symbols', 'free_spins', 'persistent_free_multiplier'],
    },
    'mahjong-ways2': {
        'factory': 'server.games.mahjong_ways2:MahjongWays2',
        'category': 'slots',
        'interaction': 'request_steps',
        'features': ['cascades', 'gold_to_wild', 'free_spins', 'free_retrigger'],
    },
}


def create_registry(game_ids=None, configs=None):
    selected = list(GAMES) if game_ids is None else list(game_ids)
    configs = configs or {}
    if not selected or len(set(selected)) != len(selected):
        raise ValueError('Select at least one game; duplicate game IDs are not allowed.')
    if set(selected) - GAMES.keys() or configs.keys() - set(selected):
        raise ValueError('Unknown game or configuration for an unselected game.')
    registry = Registry()
    for game_id in selected:
        spec = GAMES[game_id]
        module, name = spec['factory'].split(':')
        game = getattr(import_module(module), name)(configs.get(game_id))
        if game.game_id != game_id:
            raise ValueError('Catalog and engine game IDs must match.')
        registry.register(game, metadata={key: spec[key] for key in
                          ('category', 'interaction', 'features')})
    return registry
