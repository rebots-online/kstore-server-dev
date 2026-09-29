import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock, MagicMock
from kstore import gpu, embedding, config, worker

class GpuTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        values = dict(GPU_STATE_PATH=str(Path(self.tmp.name)/'gpu.json'), MINER_EXE='/bin/miner', MINER_SERVICE='miner.service',GPU_INDEX=0,GPU_WINDOW=60,GPU_COOLDOWN=300,GPU_MIN_FREE_MB=6500,GPU_RELEASE_TIMEOUT=.01,GPU_DISPLAY_ALLOWLIST=('gnome-remote-desktop-daemon','Xorg','Xwayland'))
        self.patches = [patch.object(config,k,v,create=True) for k,v in values.items()]
        for p in self.patches:
            p.start();self.addCleanup(p.stop)
        self.idle={'uuid':'gpu-test','free_mb':7000,'processes':[]}
        self.probe=patch.object(gpu,'probe',return_value=self.idle).start();self.addCleanup(patch.stopall)
        self.unload=patch.object(gpu,'unload_embedder').start()
        self.command=patch.object(gpu,'command',return_value='').start()

    def write_state(self, **extra):
        state=dict(restore_mining=True,owner_pid=99999999,owner_start='old',phase='embedding')
        state.update(extra)
        Path(config.GPU_STATE_PATH).write_text(json.dumps(state))

    def test_idle_gpu_never_starts_miner(self):
        with gpu.GpuLease():pass
        self.command.assert_not_called()

    def test_unknown_workload_defers_without_signal(self):
        self.probe.return_value=dict(self.idle,processes=[{'pid':8,'exe':'other'}])
        with patch.object(gpu,'identity',return_value=('/bin/other','1')):
            with self.assertRaises(gpu.GpuBusy):
                with gpu.GpuLease():pass
        self.command.assert_not_called()

    def test_exact_executable_not_basename(self):
        lease=gpu.GpuLease()
        with patch.object(gpu,'identity',return_value=('/untrusted/miner','1')):
            with self.assertRaises(gpu.GpuBusy):
                lease.miners(dict(self.idle,processes=[{'pid':8,'exe':'/untrusted/miner'}]))

    def test_departed_pid_is_stale_accounting_not_unknown_workload(self):
        snap=dict(self.idle,processes=[{'pid':99999999,'exe':'/bin/miner'}])
        with patch.object(gpu,'identity',return_value=None):
            self.assertEqual(gpu.GpuLease().miners(snap),[])

    def test_live_unreadable_pid_still_defers(self):
        snap=dict(self.idle,processes=[{'pid':gpu.os.getpid(),'exe':'/bin/miner'}])
        with patch.object(gpu,'identity',return_value=None):
            with self.assertRaises(gpu.GpuBusy):gpu.GpuLease().miners(snap)

    def test_dead_owner_restarts_and_persists_cooldown(self):
        self.write_state()
        miner=dict(self.idle,processes=[{'pid':8,'exe':'/bin/miner'}])
        self.probe.side_effect=[self.idle,miner]
        with patch.object(gpu,'identity',return_value=(str(Path('/bin/miner').resolve()),'1')):
            gpu.GpuLease().recover()
        self.command.assert_called_once_with('sudo','-n','systemctl','start','miner.service')
        state=json.loads(Path(config.GPU_STATE_PATH).read_text())
        self.assertFalse(state['restore_mining'])
        self.assertGreater(state['cooldown_until'],gpu.time.time())

    def test_failed_restart_retains_intent(self):
        self.write_state()
        self.command.side_effect=RuntimeError('service unavailable')
        with self.assertRaises(RuntimeError):gpu.GpuLease().recover()
        self.assertTrue(json.loads(Path(config.GPU_STATE_PATH).read_text())['restore_mining'])

    def test_cancel_works_while_lease_locked(self):
        self.write_state()
        lease=gpu.GpuLease();lease._lock()
        try:
            gpu.GpuLease().recover(cancel=True)
            lease.restore()
        finally:lease._unlock()
        self.command.assert_not_called()
        self.assertFalse(json.loads(Path(config.GPU_STATE_PATH).read_text())['restore_mining'])

    def test_live_owner_released_lock_retries_owed_restoration(self):
        self.write_state(owner_pid=gpu.os.getpid(),owner_start=gpu.owner_identity(gpu.os.getpid()))
        miner=dict(self.idle,processes=[{'pid':8,'exe':'/bin/miner'}])
        self.probe.side_effect=[self.idle,miner]
        with patch.object(gpu,'identity',return_value=(str(Path('/bin/miner').resolve()),'1')):
            gpu.GpuLease().recover()
        self.command.assert_called_once_with('sudo','-n','systemctl','start','miner.service')
        self.assertFalse(json.loads(Path(config.GPU_STATE_PATH).read_text())['restore_mining'])

    def test_live_owner_without_intent_is_successful_noop(self):
        self.write_state(owner_pid=gpu.os.getpid(),owner_start=gpu.owner_identity(gpu.os.getpid()),restore_mining=False,phase='idle')
        gpu.GpuLease().recover()
        self.command.assert_not_called()
        self.unload.assert_not_called()
        self.probe.assert_not_called()

    def test_active_lease_lock_defers_recovery_even_with_intent(self):
        self.write_state(owner_pid=gpu.os.getpid(),owner_start=gpu.owner_identity(gpu.os.getpid()))
        lease=gpu.GpuLease();lease._lock()
        try:
            with self.assertRaises(gpu.GpuBusy):gpu.GpuLease().recover()
        finally:lease._unlock()
        self.command.assert_not_called()
        self.assertTrue(json.loads(Path(config.GPU_STATE_PATH).read_text())['restore_mining'])

    def test_cooldown_defers(self):
        self.write_state(restore_mining=False,cooldown_until=gpu.time.time()+100)
        with self.assertRaises(gpu.GpuBusy):
            with gpu.GpuLease():pass
        self.command.assert_not_called()

    def test_exception_releases_flock(self):
        with self.assertRaises(ValueError):
            with gpu.GpuLease():raise ValueError('embedding failed')
        with gpu.GpuLease():pass

    def test_miner_term_is_preceded_by_durable_intent(self):
        pid=gpu.os.getpid()
        miner=dict(self.idle,processes=[{'pid':pid,'exe':'/bin/miner'}])
        self.probe.side_effect=[miner,self.idle,self.idle,miner]
        ident=(str(Path('/bin/miner').resolve()),'1')
        def observe(*args):
            if 'kill' in args:
                state=json.loads(Path(config.GPU_STATE_PATH).read_text())
                self.assertTrue(state['restore_mining'])
                self.assertEqual(state['miners'][0]['identity'],list(ident))
                self.assertIn('-TERM',args)
            return ''
        self.command.side_effect=observe
        with patch.object(gpu,'identity',return_value=ident):
            with gpu.GpuLease():pass
        self.assertTrue(any('kill' in call.args for call in self.command.call_args_list))
        self.assertTrue(any('start' in call.args for call in self.command.call_args_list))

    def test_worker_failure_returns_claimed_jobs_to_queue(self):
        w=worker.EmbeddingWorker()
        w.conn=MagicMock();w.qc=MagicMock()
        job=dict(entity_uuid='00000000-0000-0000-0000-000000000001',model=config.EMBED_MODEL,collection=config.COLLECTION,attempts=2)
        cur=w.conn.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value=[job]
        w.qc.get_collection.side_effect=RuntimeError('unavailable')
        self.assertEqual(w.run_once(),0)
        updates=[c for c in w.conn.execute.call_args_list if "state='pending'" in c.args[0]]
        self.assertEqual(len(updates),1)
        self.assertEqual(updates[0].args[1][0],40)
        self.assertEqual(updates[0].args[1][1],'RuntimeError')

    def test_worker_records_safe_scheduler_reason(self):
        w=worker.EmbeddingWorker();w.conn=MagicMock();w.qc=MagicMock()
        job=dict(entity_uuid='00000000-0000-0000-0000-000000000001',model=config.EMBED_MODEL,collection=config.COLLECTION,attempts=0)
        w.conn.cursor.return_value.__enter__.return_value.fetchall.return_value=[job]
        w.qc.get_collection.side_effect=gpu.GpuBusy('GPU release timeout: Unowned GPU process 123')
        self.assertEqual(w.run_once(),0)
        updates=[c for c in w.conn.execute.call_args_list if "state='pending'" in c.args[0]]
        self.assertEqual(updates[0].args[1][1],'GpuBusy: GPU release timeout: Unowned GPU process 123')

    def test_worker_success_requires_verified_readback(self):
        w=worker.EmbeddingWorker();w.conn=MagicMock();w.qc=MagicMock()
        content='verbatim event'
        job=dict(entity_uuid='00000000-0000-0000-0000-000000000001',model=config.EMBED_MODEL,collection=config.COLLECTION,attempts=0,content=content,content_sha256=worker.hashlib.sha256(content.encode()).hexdigest(),dims=config.EMBED_DIMS,path='event',source_type='activity',breadcrumb='',parent_uuid='00000000-0000-0000-0000-000000000002',revision=1,chunk_ix=0)
        w.conn.cursor.return_value.__enter__.return_value.fetchall.return_value=[job]
        w.qc.get_collection.return_value.config.params.vectors.size=config.EMBED_DIMS
        vector=[0.0]*config.EMBED_DIMS
        point=Mock(id=job['entity_uuid'],payload={'content':content,'content_sha256':job['content_sha256']},vector=vector)
        w.qc.retrieve.return_value=[point]
        with patch.object(worker,'GpuLease') as lease,patch.object(worker,'embed',return_value=[vector]):
            lease.return_value.__enter__.return_value.deadline=1
            self.assertEqual(w.run_once(),1)
        self.assertTrue(any("state='complete'" in c.args[0] for c in w.conn.execute.call_args_list))
        w.conn.reset_mock()
        w.conn.cursor.return_value.__enter__.return_value.fetchall.return_value=[job]
        point.payload['content']='different bytes'
        with patch.object(worker,'GpuLease'),patch.object(worker,'embed',return_value=[vector]):
            self.assertEqual(w.run_once(),0)
        self.assertFalse(any("state='complete'" in c.args[0] for c in w.conn.execute.call_args_list))

    def test_embedding_validation_and_unload_request(self):
        response=Mock()
        response.json.return_value={'embeddings':[[math.nan]*config.EMBED_DIMS]}
        with patch.object(embedding.httpx,'post',return_value=response) as request:
            with self.assertRaises(embedding.EmbeddingError):embedding._post(['a'],1)
            self.assertEqual(request.call_args.kwargs['json']['keep_alive'],0)
        response.json.return_value={'embeddings':[[0.0]*(config.EMBED_DIMS-1)]}
        with patch.object(embedding.httpx,'post',return_value=response):
            with self.assertRaises(embedding.EmbeddingError):embedding._post(['a'],1)

if __name__=='__main__':unittest.main()
