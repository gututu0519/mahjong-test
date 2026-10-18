"""Explicit game allowlist. Adding games never requires changing wallet code."""
from importlib import import_module
from server.core.contracts import Registry


GAMES = {
    'tower-run-treasure-steps': {
        'factory': 'server.games.tower_run_treasure_steps:TowerRunTreasureSteps',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['cascades', 'anywhere_pays', 'per_bet_progress', 'wild_rift', 'global_multiplier', 'hold_and_spin', 'chests', 'keys', 'go_ultra'],
    },
    'great-game-serengeti': {
        'factory': 'server.games.great_game_serengeti:GreatGameSerengeti',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['paylines', 'hunt', 'collectors', 'multiplicative_wilds', 'stampede', 'free_spins', 'free_retrigger', 'lion_bar', 'buy_bonus'],
    },
    'dr-zappo': {
        'factory': 'server.games.dr_zappo:DrZappo',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['paylines', 'reflected_lasers', 'additive_wild_multipliers', 'feature_spins', 'free_spins', 'free_retrigger', 'buy_bonus'],
    },
    'le-vampire': {
        'factory': 'server.games.le_vampire:LeVampire',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['clusters', 'super_cascades', 'golden_squares', 'blood_squares', 'collectors', 'multipliers', 'free_spins', 'free_retrigger', 'buy_bonus'],
    },
    'wicked-grin': {
        'factory': 'server.games.wicked_grin:WickedGrin',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['symbol_count', 'cascades', 'expanding_coins', 'multipliers', 'feature_spins', 'free_spins', 'free_retrigger', 'buy_bonus'],
    },
    'roma-x-10000': {
        'factory': 'server.games.roma_x_10000:RomaX10000',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['paylines', 'cascades', 'free_spins', 'free_retrigger', 'battle_bonus', 'bonus_wheel', 'buy_bonus'],
    },
    'money-pot-deluxe': {
        'factory': 'server.games.money_pot_deluxe:MoneyPotDeluxe',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['paylines', 'money_collect', 'mystery', 'hold_and_respin', 'jackpot', 'extra_bet'],
    },
    '3-billion-vaults': {
        'factory': 'server.games.three_billion_vaults:ThreeBillionVaults',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['ways', 'moving_wild', 'free_spins', 'buy_bonus', 'jackpot', 'extra_bet'],
    },
    'jokers-fortune-winx': {
        'factory': 'server.games.jokers_fortune_winx:JokersFortuneWinX',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['paylines', 'scatter', 'multipliers', 'extra_bet'],
    },
    'fortune-gems2': {
        'factory': 'server.games.fortune_gems2:FortuneGems2',
        'category': 'slots', 'interaction': 'request_steps',
        'features': ['paylines', 'wild', 'multipliers', 'extra_bet', 'lucky_wheel'],
    },
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
