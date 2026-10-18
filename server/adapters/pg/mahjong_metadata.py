"""Local login, game-name and GameInfo responses based on user-supplied captures.

No production credentials or player identifiers are stored here.
"""

import json
from server.paths import MAHJONG_CLIENT

OPERATOR_TOKEN = 'local-demo'
SESSION_TOKEN = 'local-demo-session'
AUTH_PATH = '/web-api/auth/session/v2/verifyOperatorPlayerSession'
GAME_NAME_PATH = '/web-api/game-proxy/v2/GameName/Get'
GAME_INFO_PATH = '/game-api/74/v4/GameInfo/Get'
GAME_RULE_PATH = '/web-api/game-proxy/v2/GameRule/Get'


def get_game_rule(form):
    if form.get('atk') != [SESSION_TOKEN] or form.get('gid') != ['74']:
        return 400, {'dt': None, 'err': {'cd': 'LOCAL_SESSION_INVALID',
                                      'msg': 'Only the synthetic local session is supported.'}}
    fixture = MAHJONG_CLIENT / 'fixtures' / 'game-rule.json'
    return 200, json.loads(fixture.read_text(encoding='utf-8'))


def get_game_info(form):
    if (form.get('atk') != [SESSION_TOKEN] or form.get('btt') != ['1']
            or form.get('pf') != ['1']):
        return 400, {'dt': None, 'err': {'cd': 'LOCAL_SESSION_INVALID',
                                      'msg': 'Only the synthetic local session is supported.'}}
    fixture = MAHJONG_CLIENT / 'fixtures' / 'game-info.json'
    return 200, json.loads(fixture.read_text(encoding='utf-8'))


def get_game_names(form):
    if form.get('atk') != [SESSION_TOKEN] or form.get('gid') != ['74']:
        return 400, {'dt': None, 'err': {'cd': 'LOCAL_SESSION_INVALID',
                                      'msg': 'Only the synthetic local session is supported.'}}
    # User-supplied English capture; used as the local fallback for all locales.
    fixture = MAHJONG_CLIENT / 'fixtures' / 'game-names.en.json'
    return 200, json.loads(fixture.read_text(encoding='utf-8'))


def verify_operator_session(form):
    if (form.get('otk') != [OPERATOR_TOKEN] or form.get('os') != [SESSION_TOKEN]
            or form.get('gi') != ['74'] or form.get('btt') != ['1']):
        return 400, {'dt': None, 'err': {'cd': 'LOCAL_SESSION_INVALID',
                                      'msg': 'Only the synthetic local session is supported.'}}
    flags = dict.fromkeys(('as bf bu cl et hd il ir mr np rp sp vc we gec gsc hnp '
                           'igv pwr rcf std swf tsn grtp phtr smpo bfbli bfbsi swfbli swfbsi').split(), 0)
    flags.update(dict.fromkeys('bb gc hn ts asc hwl ign ivs sbb'.split(), 1))
    flags['cbu'] = 0
    return 200, {'dt': {
        # The local demo displays bare amounts, matching the reference UI.
        'cc': 'AUD', 'cs': '', 'ec': [],
        'gm': [{'st': 1, 'gid': 74, 'mxe': 5000,
                'rtp': {'df': {'max': 96.22, 'min': 96.22}},
                'amsg': '', 'medt': 1736316176514, 'msdt': 1736316176514,
                'mxehr': 1000000000}],
        'oj': {'jid': 1}, 'st': 1, 'tk': SESSION_TOKEN,
        'bau': 'web-api/game-proxy/', 'geu': 'game-api/74/', 'lau': 'game-api/lobby/',
        'nkn': 'Local demo', 'pcd': '100001', 'pid': '100001', 'ioph': 'local-demo',
        'occ': {'tcm': '', 'tlb': '', 'trb': '', 'tsc': 0, 'ttp': 0, 'rurl': ''},
        'uiogc': flags, 'bl': 2000, 'sdn': 'api',
    }, 'err': None}
