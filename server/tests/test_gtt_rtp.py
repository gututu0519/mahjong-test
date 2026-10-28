import copy
import json
from pathlib import Path
import secrets
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from server.core.contracts import ServiceError
from server.games.buffalo_win.engine import BuffaloWin
from server.merchant.provider import MerchantService
from server.merchant.rtp import RTPStore
from server.merchant.rtp_worker import run_once
from server.tests import test_gtt_admin as fixtures


class RTPTests(unittest.TestCase):
    def setUp(self):
        self.qa = fixtures.GTTAdminTests()
        self.qa.setUp()
        self.qa.tenant_accounts()
        self.service = self.qa.service
        models = self.qa.post('rtp/read')['models']
        self.models = {row['target_bp']: row['id'] for row in models if row['published']}
        self.assertIn(9000, self.models)
        self.assertIn(9600, self.models)
        raw = json.loads((Path(__file__).resolve().parents[2] / 'services/gtt-gateway/config/rtp-models.json').read_bytes())
        self.configs = {row['target_bp']: row['modes']['normal']['config'] for row in raw['models']}

    def tearDown(self):
        self.qa.tearDown()

    def target(self, target, scope='platform', mid='', pid='', revision=0, user='admin', expected=200):
        return self.qa.post('rtp/policy', {'scope': scope, 'merchant_id': mid, 'player_id': pid, 'game_id': 1,
            'model_id': self.models[target] if target is not None else None, 'revision': revision, 'reason': 'RTP verification change'}, user=user, expected=expected)

    def player(self, pid='player-test', mid='alpha'):
        self.qa.platform.wallet.seed(mid, pid, 2000000)
        launch = self.service.launch(mid, {'player_id': pid, 'game_id': 1})
        return parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]

    def finish(self, token, key, previous='0', buy=False):
        results = []
        for index in range(4096):
            result = self.service.spin(token, 'buffalo-win', key + str(index), previous,
                {'coin_minor': 2, 'level': 1, **({'buy_free': True} if buy and index == 0 else {})})
            results.append(result)
            previous = result['sid']
            if result['outcome']['next_phase'] == 'ready':
                return results
        self.fail('A test round did not finish.')

    def test_merchant_self_service_revisions_and_tenant_isolation(self):
        self.target(9000)
        self.target(9600, 'merchant', 'alpha', user='alpha-owner')
        self.target(9000, 'player', 'alpha', 'same-player', user='alpha-owner')
        self.target(9600, 'merchant', 'beta', user='alpha-owner', expected=403)
        self.target(9600, 'platform', user='alpha-owner', expected=403)
        self.target(9600, 'merchant', 'alpha', user='alpha-read', expected=403)
        self.target(9600, 'merchant', 'alpha', user='alpha-owner', expected=409)
        data = self.qa.post('rtp/read', {'merchant_id': 'alpha', 'player_id': 'same-player'}, user='alpha-read')
        self.assertEqual(data['players'][0]['effective']['target_bp'], 9000)
        self.assertEqual({row['merchant_id'] for row in data['merchants']}, {'alpha'})
        self.assertEqual(data['jobs'], [])
        self.target(None, 'player', 'alpha', 'same-player', revision=1, user='alpha-owner')
        with self.service.connection() as db:
            self.assertEqual(self.service.rtp.resolve(db, 'alpha', 'same-player')['target_bp'], 9600)
            self.assertEqual(self.service.rtp.resolve(db, 'beta', 'same-player')['target_bp'], 9000)

    def test_actual_statistics_use_completed_rounds_and_money_weighting(self):
        token = self.player()
        game = self.service.registry.get('buffalo-win')
        board = [3, 3, 3, 2, 3, 2, 3, 2, 3, 2, 3, 2]
        game.boards = [(board, 10, {}, {})]
        first = self.service.spin(token, 'buffalo-win', 'partial', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(first['outcome']['next_phase'], 'paid_extension')
        partial = self.qa.post('rtp/read')
        self.assertEqual(partial['summary'][0]['rounds'], 0)
        self.assertEqual(partial['open_rounds'], 1)
        last = self.finish(token, 'complete', first['sid'])[-1]
        normal = self.qa.post('rtp/read')['summary'][0]
        self.assertEqual((normal['debit_minor'], normal['credit_minor'], normal['actual_rtp']), ('20', '140', 700))
        self.service.retry('alpha', last['sid'])
        self.service.retry('alpha', last['sid'])
        self.assertEqual(self.qa.post('rtp/read')['summary'][0]['rounds'], 1)
        self.finish(token, 'purchase', last['sid'], buy=True)
        total = self.qa.post('rtp/read')['summary'][0]
        self.assertEqual((total['debit_minor'], total['credit_minor'], total['rounds']), ('1520', '140', 2))
        self.assertAlmostEqual(total['actual_rtp'], 140 / 1520 * 100)
        purchased = self.qa.post('rtp/read', {'play_mode': 'buy_free'})['summary'][0]
        self.assertEqual((purchased['rounds'], purchased['debit_minor']), (1, '1500'))
        self.assertEqual(total['target_coverage'], 0)

    def test_target_changes_engine_and_remains_pinned_through_continuation(self):
        self.target(9000)
        low, high = (BuffaloWin(configuration=self.configs[number]) for number in (9000, 9600))
        bet = {'coin_minor': 2, 'level': 1}
        seed = next(f'{index:064x}' for index in range(1000)
                    if low.step(low.initial_state('0'), bet, f'{index:064x}', 'test').event['next_phase'] != 'ready')
        token = self.player()
        real = secrets.token_hex
        with patch('server.merchant.provider.secrets.token_hex', side_effect=lambda size=None: seed if size == 32 else real(size)):
            first = self.service.spin(token, 'buffalo-win', 'before-switch', '0', bet)
        self.assertEqual(first['ruleset_id'], low.ruleset_id)
        self.assertEqual(first['rtp']['model_id'], self.models[9000])
        self.target(9600, revision=1)
        info = self.service.state(token, 'buffalo-win')
        self.assertEqual(info['rtp']['target_rtp'], 90)
        rest = self.finish(token, 'old-profile-', first['sid'])
        self.assertTrue(all(result['ruleset_id'] == low.ruleset_id for result in rest))
        after = self.service.spin(token, 'buffalo-win', 'after-switch', rest[-1]['sid'], bet)
        self.assertEqual(after['ruleset_id'], high.ruleset_id)
        self.assertEqual(after['rtp']['model_id'], self.models[9600])
        with self.service.connection() as db:
            fact = db.execute('SELECT * FROM rtp_facts WHERE round_id=?', (first['round_id'],)).fetchone()
        self.assertEqual(fact['target_bp'], 9000)
        self.assertEqual(fact['closed'], 1)

    def test_distinct_player_targets_select_distinct_real_distributions(self):
        self.target(9000, 'merchant', 'alpha', user='alpha-owner')
        self.target(9600, 'player', 'alpha', 'second-player', user='alpha-owner')
        engines = [BuffaloWin(configuration=self.configs[number]) for number in (9000, 9600)]
        bet = {'coin_minor': 2, 'level': 1}
        seed = next(f'{index:064x}' for index in range(1000)
                    if engines[0].step(engines[0].initial_state('0'), bet, f'{index:064x}', 'a').event['board']
                    != engines[1].step(engines[1].initial_state('0'), bet, f'{index:064x}', 'b').event['board'])
        one, two = self.player('first-player'), self.player('second-player')
        real = secrets.token_hex
        with patch('server.merchant.provider.secrets.token_hex', side_effect=lambda size=None: seed if size == 32 else real(size)):
            a = self.service.spin(one, 'buffalo-win', 'one', '0', bet)
            b = self.service.spin(two, 'buffalo-win', 'two', '0', bet)
        self.assertNotEqual(a['outcome']['board'], b['outcome']['board'])
        self.assertEqual([a['rtp']['model_id'], b['rtp']['model_id']], [self.models[9000], self.models[9600]])

    def test_wallet_uncertainty_restart_and_policy_change_do_not_reroll(self):
        self.target(9000)
        token = self.player()
        delegate = self.service.wallet_client
        class LostReply:
            def call(self, mid, action, payload):
                result = delegate.call(mid, action, payload)
                if action == 'debit':
                    raise ServiceError('WALLET_UNCERTAIN', 'Lost response', 503)
                return result
        self.service.wallet_client = LostReply()
        with self.assertRaises(ServiceError):
            self.service.spin(token, 'buffalo-win', 'uncertain', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(self.qa.post('rtp/read')['pending_operations'], 1)
        with self.service.connection() as db:
            operation = dict(db.execute('SELECT * FROM game_operations').fetchone())
        self.target(9600, revision=1)
        recovered = MerchantService(self.service.path, self.service.merchants)
        result = recovered.retry('alpha', operation['id'])
        self.assertEqual(result['rtp']['model_id'], self.models[9000])
        self.assertEqual(result['outcome'], json.loads(operation['candidate_json'])['event'])
        self.assertEqual(recovered.retry('alpha', operation['id']), result)
        with self.qa.platform.wallet.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM transactions WHERE kind='debit'").fetchone()[0], 1)

    def test_modes_conflict_and_original_prebet_entry_remains_available(self):
        self.target(9000)
        merchant = self.qa.control.merchant('alpha')
        url = f'http://127.0.0.1:{self.qa.platform.server_port}/api/v1/callbacks/gtt/preBetDecision'
        error = self.qa.post('merchants/update', {**merchant, 'pre_payout': {'enabled': True, 'url': url}}, expected=409)
        self.assertEqual(error['code'], 'RTP_MODE_CONFLICT')
        self.qa.post('rtp/mode', {'merchant_id': 'alpha', 'mode': 'prebet', 'url': url, 'revision': 0, 'reason': 'Explicit prebet mode'})
        self.assertTrue(self.qa.control.merchant('alpha')['pre_payout']['enabled'])
        self.target(9600, 'merchant', 'alpha', expected=409)
        self.qa.post('rtp/mode', {'merchant_id': 'alpha', 'mode': 'rtp', 'revision': 1, 'reason': 'Explicit RTP mode'})
        self.assertFalse(self.qa.control.merchant('alpha')['pre_payout']['enabled'])
        self.target(9600, 'merchant', 'alpha')

    def test_rule_metadata_matches_selected_target(self):
        self.target(9600)
        token = self.player()
        code, result, _ = self.qa.request('/web-api/game-proxy/v2/GameRule/Get', user=None,
            headers={'X-Local-Game-Session': token}, port=self.qa.gateway.server_port)
        self.assertEqual(code, 200)
        self.assertEqual(result['dt']['rtp']['Default'], {'min': 96, 'max': 96})
        self.assertTrue(all(value['rtp'] == 96 for group in result['dt']['grtpi'] for value in group['grtps']))

    def test_legacy_times_are_unknown_and_currency_totals_are_separate(self):
        token = self.player()
        self.finish(token, 'legacy')
        with self.service.connection(True) as db:
            db.execute('UPDATE game_operations SET settled_at=NULL')
            db.execute('DELETE FROM rtp_accounted_ops')
            db.execute('DELETE FROM rtp_facts')
        self.service.rtp = RTPStore(self.service)
        all_time = self.qa.post('rtp/read')
        self.assertEqual(all_time['historical_unknown_time'], 1)
        self.assertEqual(all_time['summary'][0]['rounds'], 1)
        recent = self.qa.post('rtp/read', {'from_at': int(time.time()) - 1000})
        self.assertEqual(recent['summary'][0]['rounds'], 0)
        merchant = self.qa.post('merchants/create', {'name': 'USD RTP Test', 'enabled': True, 'wallet_url': f'http://127.0.0.1:{self.qa.platform.server_port}', 'games': [1]}, expected=201)['merchant']
        usd = self.player('same-player', merchant['id'])
        self.finish(usd, 'usd')
        self.assertEqual({row['currency'] for row in self.qa.post('rtp/read')['summary']}, {'USD', 'DEMO'})

    def test_queue_failure_does_not_publish_a_model(self):
        job = self.qa.post('rtp/job', {'target_bp': 9500, 'reason': 'Test failed calibration'})
        self.qa.post('rtp/job', {'target_bp': 9500, 'reason': 'Duplicate queued job'}, expected=409)
        with patch('server.merchant.rtp_worker.calibrate', side_effect=RuntimeError('Independent validation failed')):
            self.assertTrue(run_once(self.service.rtp, workers=1))
        data = self.qa.post('rtp/read')
        row = next(row for row in data['jobs'] if row['id'] == job['id'])
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(set(self.models.values()), {model['id'] for model in data['models']})
        self.qa.post('rtp/job', {'target_bp': 9500, 'reason': 'Not authorized'}, user='alpha-owner', expected=403)

    def test_existing_restrictions_cannot_disable_merchant_self_service(self):
        # An upgraded database may retain an inert old table; it is never consulted.
        with self.service.connection(True) as db:
            db.execute('CREATE TABLE rtp_grants (merchant_id TEXT PRIMARY KEY,models_json TEXT,players INTEGER,revision INTEGER)')
            db.execute("INSERT INTO rtp_grants VALUES ('alpha','[]',0,99)")
        self.service.rtp = RTPStore(self.service)
        self.target(9000)
        self.target(9600, 'merchant', 'alpha', user='alpha-owner')
        self.target(9000, 'player', 'alpha', 'own-player', user='alpha-owner')
        self.target(None, 'player', 'alpha', 'own-player', revision=1, user='alpha-owner')
        self.target(None, 'merchant', 'alpha', revision=1, user='alpha-owner')
        url = f'http://127.0.0.1:{self.qa.platform.server_port}/api/v1/callbacks/gtt/preBetDecision'
        self.qa.post('rtp/mode', {'mode':'prebet','url':url,'revision':0,'reason':'Merchant chooses own mode'}, user='alpha-owner')
        self.qa.post('rtp/mode', {'mode':'rtp','revision':1,'reason':'Merchant chooses own model'}, user='alpha-owner')
        self.target(9600, 'merchant', 'beta', user='beta-owner')
        self.target(9000, 'player', 'beta', 'own-player', user='beta-owner')
        self.qa.post('rtp/grant', {'merchant_id':'alpha','models':[],'players':False}, expected=404)
        self.qa.post('rtp/grant', {}, user='alpha-owner', expected=404)
        self.assertTrue(all('grant' not in row for row in self.qa.post('rtp/read')['merchants']))

    def test_new_merchant_can_set_own_and_player_targets_immediately(self):
        created = self.qa.post('merchants/create', {'name':'Independent Partner','enabled':True,
            'wallet_url':f'http://127.0.0.1:{self.qa.platform.server_port}','games':[1]}, expected=201)
        mid = created['merchant']['id']
        self.qa.control.create_user('admin', 'new-owner', 'merchant_admin', password=fixtures.PASSWORD, merchant_id=mid)
        self.target(9600, 'merchant', mid, user='new-owner')
        self.target(9000, 'player', mid, 'new-player', user='new-owner')
        self.target(9000, 'merchant', 'alpha', user='new-owner', expected=403)
        with self.service.connection() as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='rtp_grants'").fetchone())

    def test_prebet_round_finishes_with_original_plan_after_mode_switch(self):
        self.target(9600)
        url = f'http://127.0.0.1:{self.qa.platform.server_port}/api/v1/callbacks/gtt/preBetDecision'
        self.qa.post('rtp/mode', {'merchant_id': 'alpha', 'mode': 'prebet', 'url': url, 'revision': 0, 'reason': 'Start prebet test round'})
        self.qa.platform.wallet.seed('alpha', 'mode-player', 2000000)
        self.qa.platform.wallet.bind_prebet_player('alpha', 'mode-player', 'external-mode')
        launched = self.service.launch('alpha', {'player_id': 'mode-player', 'external_username': 'external-mode'})
        token = parse_qs(urlsplit(launched['launch_url']).query)['ops'][0]
        self.service.registry.get('buffalo-win').boards = [([3,3,3,2,3,2,3,2,3,2,3,2], 10, {}, {})]
        first = self.service.spin(token, 'buffalo-win', 'prebet-first', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(first['outcome']['next_phase'], 'paid_extension')
        self.qa.post('rtp/policy', {'scope':'merchant','merchant_id':'alpha','model_id':self.models[9600],
            'revision':0,'activate_rtp':True,'mode_revision':1,'reason':'Merchant saves RTP in one action'},user='alpha-owner')
        self.assertEqual(self.service.state(token, 'buffalo-win')['rtp']['mode'], 'prebet')
        last = self.finish(token, 'prebet-finish', first['sid'])[-1]
        self.assertEqual(last['rtp']['mode'], 'prebet')
        self.assertEqual(last['ruleset_id'], first['ruleset_id'])
        after = self.service.spin(token, 'buffalo-win', 'new-rtp-round', last['sid'], {'coin_minor': 2, 'level': 1})
        self.assertEqual(after['rtp']['model_id'], self.models[9600])
        self.assertEqual(after['rtp']['target_rtp'], 96)

    def test_quick_save_validates_before_changing_mode(self):
        url = f'http://127.0.0.1:{self.qa.platform.server_port}/api/v1/callbacks/gtt/preBetDecision'
        self.qa.post('rtp/mode', {'merchant_id':'alpha','mode':'prebet','url':url,'revision':0,'reason':'Configure original prebet'})
        request={'scope':'merchant','merchant_id':'alpha','model_id':self.models[9000],'revision':0,
                 'activate_rtp':True,'mode_revision':1,'reason':'Save merchant RTP'}
        self.qa.post('rtp/policy',{**request,'model_id':'missing-model'},user='alpha-owner',expected=400)
        self.qa.post('rtp/policy',{**request,'mode_revision':0},user='alpha-owner',expected=409)
        self.assertTrue(self.qa.control.merchant('alpha')['pre_payout']['enabled'])
        with self.service.connection() as db:
            self.assertIsNone(self.service.rtp.resolve(db,'alpha')['target_bp'])
        self.qa.post('rtp/policy',request,user='alpha-owner')
        self.assertFalse(self.qa.control.merchant('alpha')['pre_payout']['enabled'])
        with self.service.connection() as db:
            self.assertEqual(self.service.rtp.mode(db,'alpha'),('rtp',2))
            self.assertEqual(self.service.rtp.resolve(db,'alpha')['target_bp'],9000)

    def test_publish_racing_with_generation_preserves_reserved_version(self):
        self.target(9000)
        token = self.player()
        original = self.service.prebet.candidate
        def racing(*args, **kwargs):
            self.target(9600, revision=1)
            return original(*args, **kwargs)
        with patch.object(self.service.prebet, 'candidate', side_effect=racing):
            result = self.service.spin(token, 'buffalo-win', 'race', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(result['rtp']['model_id'], self.models[9000])
        with self.service.connection() as db:
            self.assertEqual(self.service.rtp.resolve(db, 'alpha')['target_bp'], 9600)

    def test_incomplete_calibration_report_cannot_be_imported(self):
        report = json.loads((Path(__file__).resolve().parents[2] / 'services/gtt-gateway/config/rtp-models.json').read_bytes())['models'][0]
        report['modes']['normal']['validation']['rounds'] = 10
        with self.assertRaises(ServiceError) as error:
            self.service.rtp.import_model(report, 'system', publish=True)
        self.assertEqual(error.exception.code, 'RTP_MODEL_INVALID')

    def test_reserved_bet_cannot_use_other_feature_distribution(self):
        self.target(9000)
        token = self.player()
        with patch.object(self.service.prebet, 'candidate', side_effect=ServiceError('TEMPORARY', 'Retry preparation', 503)):
            with self.assertRaises(ServiceError):
                self.service.spin(token, 'buffalo-win', 'prepare', '0', {'coin_minor': 2, 'level': 1})
        self.target(9600, revision=1)
        self.assertEqual(self.service.state(token, 'buffalo-win')['rtp']['target_rtp'], 90)
        with self.assertRaises(ServiceError) as error:
            self.service.spin(token, 'buffalo-win', 'buy-instead', '0', {'coin_minor': 2, 'level': 1, 'buy_free': True})
        self.assertEqual(error.exception.code, 'ROUND_PREPARING')
        result = self.service.spin(token, 'buffalo-win', 'prepare', '0', {'coin_minor': 2, 'level': 1})
        self.assertEqual(result['rtp']['model_id'], self.models[9000])

    def test_disabled_merchant_can_read_game_and_rtp_views(self):
        with self.qa.control.connection(True) as db:
            db.execute("UPDATE merchants SET enabled=0 WHERE id='alpha'")
        self.assertEqual(self.qa.post('games', user='alpha-read')['games'][0]['id'], 1)
        self.assertEqual(self.qa.post('rtp/read', user='alpha-read')['merchants'][0]['merchant_id'], 'alpha')


if __name__ == '__main__':
    unittest.main()
