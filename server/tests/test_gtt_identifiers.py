import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from server.core.contracts import ServiceError
from server.merchant.common import signed_headers
from server.merchant.control import ControlStore, MerchantDirectory
from server.merchant.identifiers import GAME_CODES, game_code, game_number
from server.merchant.migrate_identifiers import migrate_identifiers
from server.merchant.mock_wallet import MockWallet
from server.merchant.provider import MerchantService
from server.tests.test_gtt_merchant import configuration, wallet_payload
from server.tests.test_gtt_admin import PASSWORD
from server.tests.test_buffalo_engine import Scripted
from urllib.parse import parse_qs, urlsplit


class MerchantIdentifierTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.store=ControlStore(self.root/'control.sqlite3')
        self.store.migrate(configuration()['merchants'])
        self.directory=MerchantDirectory(self.store)
        self.wallet=MockWallet(self.root/'wallet.sqlite3', self.directory)
        self.service=MerchantService(self.root/'gateway.sqlite3',self.directory,Scripted(),self.wallet)
        self.store.create_user('system','alpha-owner','merchant_admin',PASSWORD,merchant_id='alpha')
        self.store.create_user('system','alpha-team','merchant_viewer',PASSWORD,merchant_id='alpha')
        self.paths=(self.store.path,self.service.path,self.wallet.path)
        for merchant in ('alpha','beta'):
            self.wallet.seed(merchant,'same-player',200000)

    def tearDown(self): self.temp.cleanup()

    def test_numeric_game_contract_and_name_login(self):
        self.assertEqual(game_code(1),'buffalo-win')
        self.assertEqual([game_number(code) for code in GAME_CODES],list(range(1,len(GAME_CODES)+1)))
        self.assertEqual(self.service.catalog('alpha')['games'][0]['id'],1)
        for bad in ('buffalo-win','1',True,1.0,0,-1,None):
            with self.subTest(value=bad),self.assertRaises(ServiceError):
                self.service.launch('alpha',{'player_id':'same-player','game_id':bad})
        self.assertEqual(self.service.launch('alpha',{'player_id':'same-player','game_id':1})['game_id'],1)
        _,session=self.store.login('alpha',PASSWORD,'local',merchant_login=True)
        self.assertEqual(session['user']['login_name'],'alpha')
        with self.assertRaises(ServiceError):self.store.login('alpha-owner',PASSWORD,'local',merchant_login=True)
        self.store.login('alpha-team',PASSWORD,'local',merchant_login=True)
        merchant=self.store.merchant('alpha')
        self.store.save_profile('alpha-owner','alpha',{'id':'alpha','version':merchant['version'],'name':'华盛商户'})
        self.store.login('华盛商户',PASSWORD,'local',merchant_login=True)
        with self.assertRaises(ServiceError):self.store.login('alpha',PASSWORD,'local',merchant_login=True)
        with self.assertRaises(ServiceError):
            self.store.save_merchant('system',{'name':'华盛商户','enabled':True,'wallet_url':'https://wallet.example','games':[1]}, {1},create=True)

    def test_sequential_numbers_and_automatic_primary_login(self):
        payload={'name':'商户 A','enabled':True,'wallet_url':'https://wallet.example','games':[1]}
        first=self.store.save_merchant('system',payload,{1},create=True)
        second=self.store.save_merchant('system',{**payload,'name':'商户 B'},{1},create=True)
        self.assertEqual([first['merchant']['id'],second['merchant']['id']],['GTT000001','GTT000002'])
        _,session=self.store.login('商户 A',first['login']['temporary_password'],'local',merchant_login=True)
        self.assertEqual(session['user']['merchant_id'],'GTT000001')
        self.assertEqual(first['merchant']['games'],[1])
        self.assertEqual(len(first['keys']['merchant_secret']),64)
        with self.store.connection(True) as db:
            db.execute('DELETE FROM merchant_signing_credentials WHERE merchant_id=?',('GTT000002',))
            db.execute('DELETE FROM merchant_prebet_settings WHERE merchant_id=?',('GTT000002',))
            db.execute('DELETE FROM admin_users WHERE merchant_id=?',('GTT000002',))
            db.execute('DELETE FROM merchants WHERE id=?',('GTT000002',))
        third=self.store.save_merchant('system',{**payload,'name':'商户 C'},{1},create=True)
        self.assertEqual(third['merchant']['id'],'GTT000003')

    def test_offline_migration_preserves_pending_settlement_sessions_and_keys(self):
        launch=self.service.launch('alpha',{'player_id':'same-player','game_id':1})
        game_token=parse_qs(urlsplit(launch['launch_url']).query)['ops'][0]
        admin_token,_=self.store.login('alpha',PASSWORD,'local',merchant_login=True)
        secret=self.store.merchant('alpha',private=True)['merchant_secret']
        self.service.authenticate(signed_headers('alpha',secret,'/gtt/v1/games/list',b'{}'),'/gtt/v1/games/list',b'{}',self.directory)
        wallet=self.wallet
        class LostReply:
            def call(self,merchant,action,payload):
                result=wallet.call(merchant,action,payload)
                if action=='debit':raise ServiceError('WALLET_UNCERTAIN','Lost reply',503)
                return result
        self.service.wallet_client=LostReply()
        with self.assertRaises(ServiceError):self.service.spin(game_token,'buffalo-win','migrate-pending','0',{})
        before=self.wallet.call('alpha','balance',wallet_payload())['balance_minor']
        with self.service.connection() as db:
            operation=db.execute('SELECT id FROM game_operations').fetchone()[0]
        config=self.root/'sandbox.json';config.write_text(json.dumps({'sandbox_merchant':'alpha'}))
        bootstrap=self.root/'bootstrap.json';bootstrap.write_text(json.dumps({'username':'alpha-owner','password':PASSWORD,'merchant_id':'alpha'}))
        result=migrate_identifiers(*self.paths,config,[bootstrap])
        self.assertEqual(result['mapping'],{'alpha':'GTT000001','beta':'GTT000002'})
        self.assertTrue(Path(result['backup']).is_dir())
        self.assertEqual(json.loads(config.read_text())['sandbox_merchant'],'GTT000001')
        self.assertEqual(json.loads(bootstrap.read_text())['username'],'alpha')
        self.assertEqual(self.store.merchant('GTT000001',private=True)['merchant_secret'],secret)
        self.assertEqual(self.store.session(admin_token)['user']['merchant_id'],'GTT000001')
        self.store.login('alpha',PASSWORD,'local',merchant_login=True)
        recovered=MerchantService(self.service.path,self.directory,Scripted(),MockWallet(self.wallet.path,self.directory))
        with self.assertRaises(ServiceError) as invalid:
            recovered.authenticate(signed_headers('alpha',secret,'/gtt/v1/games/list',b'{}'),'/gtt/v1/games/list',b'{}',self.directory)
        self.assertEqual(invalid.exception.code,'AUTH_INVALID')
        recovered.authenticate(signed_headers('GTT000001',secret,'/gtt/v1/games/list',b'{}'),'/gtt/v1/games/list',b'{}',self.directory)
        beta_credentials=json.loads(Path(result['provisioned_credentials'][0]).read_text(encoding='utf-8'))
        self.store.login(beta_credentials['username'],beta_credentials['password'],'local',merchant_login=True)
        self.assertEqual(recovered.wallet(game_token)['balance_minor'],before)
        recovered.retry('GTT000001',operation)
        recovered.retry('GTT000001',operation)
        self.assertEqual(recovered.operations('GTT000001',{})['operations'][0]['game_id'],1)
        with self.wallet.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM transactions WHERE kind='debit'").fetchone()[0],1)
        again=migrate_identifiers(*self.paths,config,[bootstrap])
        self.assertEqual(result['mapping'],again['mapping'])
        for path in self.paths:
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                    quoted='"'+table.replace('"','""')+'"'
                    if 'merchant_id' in {row[1] for row in db.execute(f'PRAGMA table_info({quoted})')}:
                        self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {quoted} WHERE merchant_id IN (?,?)',('alpha','beta')).fetchone()[0],0)

    def test_migration_rolls_back_all_databases_on_failure(self):
        self.wallet.call('alpha','debit',wallet_payload())
        allocate=ControlStore.allocate_merchant_id
        count=0
        def fail_after_first(db):
            nonlocal count
            count+=1
            if count==2:raise RuntimeError('Injected migration failure')
            return allocate(db)
        with patch.object(ControlStore,'allocate_merchant_id',side_effect=fail_after_first):
            with self.assertRaises(RuntimeError):migrate_identifiers(*self.paths)
        self.assertIsNotNone(self.store.merchant('alpha'))
        self.assertIsNone(self.store.merchant('GTT000001'))
        self.assertEqual(self.wallet.call('alpha','balance',wallet_payload())['balance_minor'],199900)
        self.assertEqual(self.store.session(self.store.login('alpha',PASSWORD,'local',merchant_login=True)[0])['user']['merchant_id'],'alpha')
