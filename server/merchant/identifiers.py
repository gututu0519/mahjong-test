"""Stable public GTT numbers; engine codes and original client routes stay internal."""
from server.core.contracts import ServiceError

# Append new games only. Never reorder or reuse a published number.
GAME_CODES = (
    'buffalo-win', 'captains-bounty', 'fortune-rabbit', 'wild-bandito',
    'tower-run-treasure-steps', 'great-game-serengeti', 'dr-zappo', 'le-vampire',
    'wicked-grin', 'roma-x-10000', 'money-pot-deluxe', '3-billion-vaults',
    'jokers-fortune-winx', 'fortune-gems2', 'super-ace', 'big-bass-bonanza',
    'sweet-bonanza-pop', 'gates-of-olympus', 'mahjong-ways2',
)


def game_number(code):
    try:
        return GAME_CODES.index(code) + 1
    except ValueError:
        raise ServiceError('GAME_NOT_FOUND', '游戏尚未分配 GTT 数字编号。', 404) from None


def game_code(number):
    if type(number) is not int or not 1 <= number <= len(GAME_CODES):
        raise ServiceError('GAME_ID_INVALID', 'game_id 须为已分配的正整数游戏编号。')
    return GAME_CODES[number - 1]


def public_result(value):
    return {**value, 'game_id': game_number(value['game_id'])} if isinstance(value.get('game_id'), str) else value
