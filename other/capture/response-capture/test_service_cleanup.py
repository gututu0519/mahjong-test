"""一键清理策略与整批确认回归；全部服务均来自临时目录和虚拟进程表。"""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from service_cleanup import ServiceCleanup
from service_runtime import ServiceError, ServiceManager


class EmptyOriginals:
    def catalog(self):
        return {'games':[]}


class SharedFixture:
    def __init__(self):
        self.executed = []
        self.failure = None
        self.states = {'advanced.postgres':'running', 'advanced.docker':'running'}

    def snapshot(self, inventory=None):
        return {'services':[
            {'id':'advanced.postgres','name':'共享 PostgreSQL','status':self.states['advanced.postgres'],
             'pid':None,'port':15432,'can_start':False,'can_stop':True,'method':'docker-container','impact':{'dependents':[]}},
            {'id':'advanced.docker','name':'Docker','status':self.states['advanced.docker'],
             'pid':None,'can_start':False,'can_stop':True},
        ]}

    def prepare(self, identifier, action, inventory=None):
        return {'id':identifier,'action':action,'identity_fingerprint':identifier+':'+self.states[identifier],
                'warnings':['关闭共享依赖会中断依赖它的服务。'],
                'targets':[{'id':identifier,'name':identifier,'mode':'shared'}]}

    def execute(self, plan):
        self.executed.append(plan['id'])
        if plan['id'] == self.failure:
            raise ValueError('夹具：共享服务拒绝关闭')
        # 提交关闭不等于已经退出，保持实际状态直到后续快照确认。
        return {'ok':True,'state':'stopping','message':'已提交共享服务关闭'}


class ServiceCleanupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='service-cleanup-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.current = {'processes':[],'listeners':[]}
        self.effects, self.spawned = [], []
        self.fail_pid, self.after_action = None, None
        self.capture_states = {990001:'idle',990002:'idle',990003:'active',990004:'unknown',990005:'idle'}
        self.shared = SharedFixture()
        self.manager = ServiceManager(self.repo, capture_port=18095, control_port=18096,
            owner_chat='fixture-current-chat', inventory=lambda:copy.deepcopy(self.current),
            spawner=self.forbidden_spawn, terminator=self.terminate, original_games=EmptyOriginals(),
            shared_services=self.shared, worktree_provider=lambda:[self.repo], health=self.health,
            start_background=False)
        self.addCleanup(self.manager.close)
        self.manager._shutdown_capture = lambda record:self.stop_process('shutdown',record['pid'])
        self.manager.control_pid = 999999
        self.origin = 'http://127.0.0.1:18097'
        entry = self.repo / 'other/capture/response-capture/app.py'
        for pid, port in [(990001,18095),(990002,18097),(990003,18098),(990004,18099),(990005,18100)]:
            self.add_process(pid,['python',str(entry),'--port',str(port)],port)
        self.add_process(990006,['node',str(self.repo / 'other/tooling/feature-maintenance/watch.mjs'),
                                '--capture-url','http://127.0.0.1:18095'])
        self.add_process(990007,['node',str(self.repo / 'other/tooling/start-source.mjs'),'gateway'],18110)
        self.cleanup = ServiceCleanup(self.manager,capture_probe=lambda record:self.capture_states.get(record['pid'],'unknown'))
        self.sentinels = {}
        for relative in ('other/capture/response-capture/captures/fixture/body.bin',
                         'other/diagnostics/original-fixture/client/index.html', 'gateway/instance/fixture-database.bin'):
            path = self.repo / relative
            path.parent.mkdir(parents=True,exist_ok=True)
            content = ('保留的用户数据：'+relative).encode('utf-8')
            path.write_bytes(content)
            self.sentinels[path] = content

    def add_process(self,pid,command,port=None):
        self.current['processes'].append({'pid':pid,'parent':42,'created':'2026-11-24T01:00:00+00:00',
                                         'command':command,'executable':command[0],'cwd':str(self.repo)})
        if port:
            self.current['listeners'].append({'pid':pid,'port':port,'address':'127.0.0.1'})

    def health(self,record):
        state = self.capture_states.get(record.get('pid'))
        if state not in ('idle','active'):
            return {}
        return {'pid':record['pid'],'created':record['created'],'active_sessions':int(state=='active'),
                'capabilities':{'shutdown':True}}

    def forbidden_spawn(self,*args,**kwargs):
        self.spawned.append((args,kwargs))
        raise AssertionError('批量清理不能启动新服务')

    def terminate(self,record,actual):
        self.stop_process('terminate',actual['pid'])

    def stop_process(self,mode,pid):
        if pid == self.fail_pid:
            raise ValueError('夹具：指定服务关闭失败')
        self.effects.append((mode,pid))
        self.current['processes'] = [p for p in self.current['processes'] if p['pid'] != pid]
        self.current['listeners'] = [p for p in self.current['listeners'] if p['pid'] != pid]
        if self.after_action:
            callback,self.after_action = self.after_action,None
            callback()

    def options(self):
        return self.cleanup.options(self.origin)['items']

    def suggested(self):
        return [item['id'] for item in self.options() if item['required_keep'] or item['default_keep']]

    def assert_data_retained(self):
        for path,content in self.sentinels.items():
            self.assertEqual(path.read_bytes(),content)

    def test_options_protect_actual_origin_active_unknown_and_controller_without_effects(self):
        items = self.options()
        by_pid = {item['pid']:item for item in items if item.get('pid')}
        self.assertTrue(by_pid[990002]['required_keep'])
        self.assertFalse(by_pid[990001]['required_keep'])
        self.assertTrue(by_pid[990003]['required_keep'])
        self.assertTrue(by_pid[990004]['required_keep'])
        self.assertTrue(by_pid[999999]['required_keep'])
        self.assertFalse(by_pid[990005]['default_keep'])
        self.assertFalse(by_pid[990007]['default_keep'])
        self.assertTrue(by_pid[990006]['default_keep'])
        by_id = {item['id']:item for item in items}
        for identifier in ('advanced.postgres','advanced.docker'):
            self.assertTrue(by_id[identifier]['default_keep'])
        self.assertEqual(len(by_pid),len([i for i in items if i.get('pid')]))
        self.assertFalse(self.effects)
        self.assertFalse(self.shared.executed)
        self.assertFalse(self.spawned)

    def test_prepare_closes_keep_dependencies_and_never_deletes_data(self):
        by_pid = {item.get('pid'):item['id'] for item in self.options()}
        prepared = self.cleanup.prepare(['external.990007','external.990006'],self.origin)
        kept = set(prepared['keep_ids'])
        self.assertTrue({by_pid[pid] for pid in (990002,990003,990004,999999)}.issubset(kept))
        self.assertTrue({'advanced.postgres','advanced.docker','external.990001'}.issubset(kept))
        self.assertEqual({target['pid'] for target in prepared['targets']},{990005})
        self.assertTrue(any('不删除' in text for text in prepared['warnings']))
        self.assertFalse(self.effects)
        self.assertFalse(self.shared.executed)
        self.assert_data_retained()

    def test_batch_receipt_is_origin_bound_expiring_single_use_and_prevalidates_every_target(self):
        keep = self.suggested()
        prepared = self.cleanup.prepare(keep,self.origin)
        with self.assertRaises(ServiceError):
            self.cleanup.execute(prepared['confirmation_id'],'http://127.0.0.1:18095')
        prepared = self.cleanup.prepare(keep,self.origin)
        self.cleanup.confirmations[prepared['confirmation_id']]['expires'] = time.monotonic()-1
        with self.assertRaises(ServiceError):
            self.cleanup.execute(prepared['confirmation_id'],self.origin)
        prepared = self.cleanup.prepare(keep,self.origin)
        process = next(p for p in self.current['processes'] if p['pid']==990007)
        original_created = process['created']
        process['created'] = '2026-11-24T05:00:00+00:00'
        with self.assertRaises(ServiceError):
            self.cleanup.execute(prepared['confirmation_id'],self.origin)
        process['created'] = original_created
        prepared = self.cleanup.prepare(keep,self.origin)
        self.capture_states[990005] = 'active'
        with self.assertRaises(ServiceError):
            self.cleanup.execute(prepared['confirmation_id'],self.origin)
        self.assertFalse(self.effects)
        self.assertFalse(self.shared.executed)
        self.assert_data_retained()

    def test_execution_only_stops_planned_exact_instances_and_token_cannot_repeat(self):
        prepared = self.cleanup.prepare(self.suggested(),self.origin)
        expected = {target['pid'] for target in prepared['targets']}
        self.assertEqual(expected,{990005,990007})
        result = self.cleanup.execute(prepared['confirmation_id'],self.origin)
        self.assertTrue(result['ok'])
        self.assertEqual(result['submitted_count'],2)
        self.assertEqual({pid for _,pid in self.effects},expected)
        self.assertEqual({p['pid'] for p in self.current['processes']},{990001,990002,990003,990004,990006})
        self.assertFalse(self.shared.executed)
        self.assertFalse(self.spawned)
        self.assert_data_retained()
        with self.assertRaises(ServiceError):
            self.cleanup.execute(prepared['confirmation_id'],self.origin)
        self.assertEqual(len(self.effects),2)

    def test_partial_failure_keeps_live_dependents_and_shared_services(self):
        self.fail_pid = 990007
        prepared = self.cleanup.prepare(['external.990006'],self.origin)
        idle_id = next(target['id'] for target in prepared['targets'] if target.get('pid') == 990005)
        result = self.cleanup.execute(prepared['confirmation_id'],self.origin)
        states = {item['id']:item['state'] for item in result['results']}
        self.assertEqual(states['external.990007'],'failed')
        self.assertEqual(states[idle_id],'stopping')
        self.assertEqual(states['advanced.postgres'],'skipped')
        self.assertEqual(states['advanced.docker'],'skipped')
        self.assertFalse(result['ok'])
        self.assertFalse(self.shared.executed)
        self.assertIn(990007,{p['pid'] for p in self.current['processes']})
        self.assert_data_retained()

    def test_process_changes_during_execution_skip_only_changed_target(self):
        prepared = self.cleanup.prepare(self.suggested(),self.origin)
        first_pid,second_pid = [target['pid'] for target in prepared['targets']]
        def replace_second():
            next(p for p in self.current['processes'] if p['pid']==second_pid)['created'] = '2026-11-24T06:00:00+00:00'
        self.after_action = replace_second
        result = self.cleanup.execute(prepared['confirmation_id'],self.origin)
        self.assertEqual([item['state'] for item in result['results']],['stopping','skipped'])
        self.assertEqual([pid for _,pid in self.effects],[first_pid])
        self.assertIn(second_pid,{p['pid'] for p in self.current['processes']})
        self.assert_data_retained()

    def test_docker_is_skipped_when_pidless_postgres_fails_or_only_submits_stop(self):
        self.current['processes'] = [p for p in self.current['processes'] if p['pid'] != 990007]
        self.current['listeners'] = [p for p in self.current['listeners'] if p['pid'] != 990007]
        keep = [item['id'] for item in self.options() if item['id'] not in ('advanced.postgres','advanced.docker')]
        for failure in ('advanced.postgres',None):
            self.shared.failure = failure
            self.shared.executed = []
            with self.subTest(failure=failure):
                prepared = self.cleanup.prepare(keep,self.origin)
                result = self.cleanup.execute(prepared['confirmation_id'],self.origin)
                states = {item['id']:item['state'] for item in result['results']}
                self.assertEqual(states['advanced.postgres'],'failed' if failure else 'stopping')
                self.assertEqual(states['advanced.docker'],'skipped')
                self.assertEqual(self.shared.executed,['advanced.postgres'])
        self.assert_data_retained()

    def test_unknown_keep_ids_and_invalid_origin_do_not_prepare_execution(self):
        for values in (['not-a-service'],[None],'all'):
            with self.subTest(values=values),self.assertRaises(ServiceError):
                self.cleanup.prepare(values,self.origin)
        for origin in ('https://127.0.0.1:18097','http://outside.invalid:18097','null'):
            with self.subTest(origin=origin),self.assertRaises(ServiceError):
                self.cleanup.options(origin)
        self.assertFalse(self.effects)
        self.assertFalse(self.shared.executed)
        self.assertFalse(self.cleanup.confirmations)

    def test_kept_child_also_protects_its_force_stoppable_parent(self):
        watch = next(p for p in self.current['processes'] if p['pid']==990006)
        watch.update(parent=990007,created='2026-11-24T02:00:00+00:00')
        prepared = self.cleanup.prepare(self.suggested(),self.origin)
        self.assertIn('external.990007',prepared['keep_ids'])
        self.assertNotIn(990007,{target.get('pid') for target in prepared['targets']})
        self.assertTrue(any('自动保留' in item.get('keep_reason','')
                            for item in prepared['kept_items'] if item['id']=='external.990007'))
        self.assertFalse(self.effects)

    def test_force_parent_and_unkept_child_are_combined_without_duplicate_stop(self):
        self.add_process(990008,['python',str(self.repo / 'other/capture/response-capture/quality_service.py')],18111)
        self.current['processes'][-1].update(parent=990007,created='2026-11-24T02:00:00+00:00')
        prepared = self.cleanup.prepare(self.suggested(),self.origin)
        self.assertNotIn(990008,{target.get('pid') for target in prepared['targets']})
        self.assertTrue(any('合并' in value for value in prepared['warnings']))
        result = self.cleanup.execute(prepared['confirmation_id'],self.origin)
        self.assertEqual(result['submitted_count'],2)
        stopped = [pid for _,pid in self.effects]
        self.assertEqual(set(stopped),{990005,990007,990008})
        self.assertEqual(len(stopped),3)
        self.assert_data_retained()

    def test_legacy_capture_becoming_active_mid_batch_is_not_force_closed(self):
        self.manager.health = lambda record:{}
        self.add_process(990008,['python',str(self.repo / 'other/capture/response-capture/app.py'),'--port','18101'],18101)
        self.capture_states[990008] = 'idle'
        prepared = self.cleanup.prepare(self.suggested(),self.origin)
        first_pid = prepared['targets'][0]['pid']
        protected = next(target for target in prepared['targets'] if target.get('pid') != first_pid
                         and self.capture_states.get(target.get('pid'))=='idle')
        self.after_action = lambda:self.capture_states.update({protected['pid']:'active'})
        result = self.cleanup.execute(prepared['confirmation_id'],self.origin)
        states = {item['id']:item['state'] for item in result['results']}
        self.assertEqual(states[protected['id']],'skipped')
        self.assertNotIn(protected['pid'],{pid for _,pid in self.effects})
        self.assertIn(protected['pid'],{p['pid'] for p in self.current['processes']})
        self.assert_data_retained()

    def test_shared_timeout_keeps_prior_partial_results_and_continues_safe_skips(self):
        def timeout(plan):
            self.shared.executed.append(plan['id'])
            raise subprocess.TimeoutExpired('fixture-shared-stop',.1)
        self.shared.execute = timeout
        prepared = self.cleanup.prepare(['external.990006'],self.origin)
        result = self.cleanup.execute(prepared['confirmation_id'],self.origin)
        states = {item['id']:item['state'] for item in result['results']}
        self.assertEqual(result['submitted_count'],2)
        self.assertEqual(states['advanced.postgres'],'failed')
        self.assertEqual(states['advanced.docker'],'skipped')
        self.assertEqual(result['failed_count'],1)
        self.assertEqual(result['skipped_count'],1)
        self.assertEqual(len(self.effects),2)
        self.assertEqual(self.shared.executed,['advanced.postgres'])
        self.assert_data_retained()

    def test_parent_force_tree_is_skipped_if_legacy_capture_child_becomes_active(self):
        self.manager.health = lambda record:{}
        child = next(p for p in self.current['processes'] if p['pid']==990005)
        child.update(parent=990007,created='2026-11-24T02:00:00+00:00')
        self.add_process(990008,['python',str(self.repo / 'other/capture/response-capture/app.py'),'--port','18101'],18101)
        self.capture_states[990008] = 'idle'
        prepared = self.cleanup.prepare(self.suggested(),self.origin)
        self.assertEqual(prepared['targets'][0]['pid'],990008)
        self.assertNotIn(990005,{target.get('pid') for target in prepared['targets']})
        self.after_action = lambda:self.capture_states.update({990005:'active'})
        result = self.cleanup.execute(prepared['confirmation_id'],self.origin)
        states = {item['id']:item['state'] for item in result['results']}
        self.assertEqual(states['external.990007'],'skipped')
        self.assertEqual({pid for _,pid in self.effects},{990008})
        self.assertTrue({990005,990007}.issubset({p['pid'] for p in self.current['processes']}))
        self.assert_data_retained()


if __name__ == '__main__':
    unittest.main()
