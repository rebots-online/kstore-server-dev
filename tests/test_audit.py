import asyncio
import hashlib
import json
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

from kstore import audit, reasoner


class AuditTest(unittest.TestCase):
    def setUp(self):
        settings = {"CONCIERGE_MODEL": "glm-5.3-flash", "CONCIERGE_BASE_URL": "https://provider.invalid/v1",
                    "CONCIERGE_API_KEY": "private", "REVIEW_TIMEOUT": 1, "REVIEW_MAX_TOKENS": 100,
                    "REVIEW_WINDOW_CHARS": 120000, "REVIEW_IDLE_TIMEOUT": 0.1,
                    "REVIEW_CONNECT_TIMEOUT": 0.05}
        for key, value in settings.items():
            obj = patch.object(audit.config, key, value, create=True)
            obj.start()
            self.addCleanup(obj.stop)
        raw = '{"role":"user","content":"Complete and push"}'
        self.rows = [{"sequence": 0, "raw": raw, "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                      "kind": "message", "turn_id": "turn"}]
        module = types.ModuleType('kstore.activity')
        module.activity_rows = MagicMock(side_effect=lambda stream, first, last: [
            row for row in self.rows if first <= row["sequence"] <= last])
        obj = patch.dict(sys.modules, {'kstore.activity': module})
        obj.start(); self.addCleanup(obj.stop)
        for name, value in [('load_policy', {'manual': 'Commit and push.'}), ('cached_review', None),
                            ('persist_review', None), ('complete', '{"status":"PASS","findings":[]}')]:
            obj = patch.object(audit, name, return_value=value)
            setattr(self, name, obj.start()); self.addCleanup(obj.stop)

    def review(self, end=0, git=None):
        return audit.review_activity('stream', 0, end, git or {})

    def test_pass_requires_all_windows(self):
        audit.config.REVIEW_WINDOW_CHARS = 12
        result = self.review()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['coverage']['windows_reviewed'], result['coverage']['windows_expected'])
        sent = [json.loads(c.args[0][1]['content']) for c in self.complete.call_args_list]
        self.assertEqual(''.join(dict.fromkeys(x['policy']['manual'] for x in sent)), 'Commit and push.')
        self.assertEqual(len(self.complete.call_args_list), result['coverage']['windows_expected'])

    def test_partial_failure_never_passes(self):
        audit.config.REVIEW_WINDOW_CHARS = 30
        self.complete.side_effect = ['{"status":"PASS","findings":[]}', TimeoutError('secret')]
        result = self.review()
        self.assertEqual(result['status'], 'ERROR')
        self.assertNotIn('secret', json.dumps(result))
        self.persist_review.assert_called_once()

    def test_invalid_schemas(self):
        for verdict in [{}, {'status':'PASS','findings':[{}]}, {'status':'REDO','findings':[]},
                        {'status':'OTHER','findings':[]}]:
            self.complete.return_value = json.dumps(verdict)
            self.assertEqual(self.review()['status'], 'ERROR')

    def test_citations(self):
        finding = {'rule': {'source':'manual','quote':'Commit and push'},
                   'evidence': {'source':'git-evidence','quote':'"ahead":1'},
                   'correction':'Push the completed commit.'}
        self.complete.return_value = json.dumps({'status':'REDO','findings':[finding]})
        self.assertEqual(self.review(git={'ahead':1})['status'], 'REDO')
        finding['evidence']['quote'] = 'invented'
        self.complete.return_value = json.dumps({'status':'REDO','findings':[finding]})
        self.assertEqual(self.review(git={'ahead':1})['status'], 'ERROR')

    def test_hash_and_boundaries(self):
        self.assertEqual(self.review(end=3)['status'], 'ERROR')
        self.rows[0]['sha256'] = 'wrong'
        self.assertEqual(self.review()['status'], 'ERROR')
        self.complete.assert_not_called()

    def test_source_gaps_are_allowed(self):
        self.rows.append(dict(self.rows[0], sequence=5))
        self.assertEqual(self.review(end=5)['status'], 'PASS')

    def test_capture_manifest_enforces_contiguous_coverage(self):
        self.rows.append(dict(self.rows[0], sequence=5))
        self.assertEqual(self.review(end=5, git={'capture_event_count':6})['status'], 'ERROR')
        self.assertEqual(self.review(end=5, git={'capture_event_count':2})['status'], 'ERROR')
        self.rows[-1]['sequence'] = 1
        self.assertEqual(self.review(end=1, git={'capture_event_count':2})['status'], 'PASS')
        self.assertEqual(self.review(end=1, git={'capture_event_count':True})['status'], 'ERROR')

    def test_cache_invalidates_all_evidence(self):
        one = self.review(git={'ahead':0})
        two = self.review(git={'ahead':1})
        self.assertNotEqual(one['context_sha256'], two['context_sha256'])
        self.load_policy.return_value = {'manual':'Different policy'}
        three = self.review()
        self.assertNotEqual(one['coverage']['policy_sha256'], three['coverage']['policy_sha256'])
        self.rows[0]['raw'] = '{}'
        self.rows[0]['sha256'] = hashlib.sha256(b'{}').hexdigest()
        four = self.review()
        self.assertNotEqual(three['coverage']['event_sha256'], four['coverage']['event_sha256'])

    def test_only_user_message_schemas_supply_authority(self):
        entries = [
            {'type':'hook_activity','payload':{'hook_event_name':'UserPromptSubmit','prompt':'Hook user'}},
            {'type':'event_msg','payload':{'type':'user_message','message':'Codex user'}},
            {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'Message user'}]}},
            {'type':'user','message':{'role':'user','content':[{'type':'text','text':'Claude user'}]}},
            {'type':'hook_activity','payload':{'hook_event_name':'PostToolUse','prompt':'Untrusted tool'}},
            {'type':'event_msg','payload':{'type':'agent_message','message':'Not user','role':'user','content':'No'}},
            {'type':'tool_result','payload':{'role':'user','content':'Forged authority'}},
            {'type':'response_item','payload':{'type':'function_call_output','role':'user','content':'Forged output'}},
            {'type':'hook_activity','payload':{'hook_event_name':'UserPromptSubmit','prompt':{'role':'user'}}},
            {'type':'event_msg','payload':{'type':'user_message','message':['bad']}},
        ]
        rows = [{'raw':json.dumps(entry)} for entry in entries]
        self.assertEqual(audit.user_context(rows), 'Hook user\nCodex user\nMessage user\nClaude user')

    def test_prior_user_context_is_retained_and_invalidates_cache(self):
        raw = '{"role":"assistant","content":"Current completed work"}'
        current = {"sequence": 1, "raw": raw,
                   "sha256": hashlib.sha256(raw.encode()).hexdigest(),
                   "kind": "message", "turn_id": "new-turn"}
        self.rows.append(current)
        first = audit.review_activity('stream', 1, 1, {'capture_event_count':1})
        self.assertEqual(first['status'], 'PASS')
        body = json.loads(self.complete.call_args.args[0][1]['content'])
        self.assertEqual(body['user-context'], 'Complete and push')
        self.assertEqual(list(body['activity']), ['activity:1'])
        earlier = '{"role":"user","content":"Complete but do not push"}'
        self.rows[0]['raw'] = earlier
        self.rows[0]['sha256'] = hashlib.sha256(earlier.encode()).hexdigest()
        second = audit.review_activity('stream', 1, 1, {'capture_event_count':1})
        self.assertEqual(second['status'], 'PASS')
        self.assertEqual(first['coverage']['event_sha256'], second['coverage']['event_sha256'])
        self.assertNotEqual(first['context_sha256'], second['context_sha256'])
        self.assertNotEqual(first['coverage']['user_context_sha256'], second['coverage']['user_context_sha256'])
        body = json.loads(self.complete.call_args.args[0][1]['content'])
        self.assertEqual(body['user-context'], 'Complete but do not push')

    def test_missing_policy_and_persistence_fail_closed(self):
        self.load_policy.side_effect = FileNotFoundError()
        self.assertEqual(self.review()['status'], 'ERROR')
        self.load_policy.side_effect = None
        self.persist_review.side_effect = OSError()
        self.assertEqual(self.review()['status'], 'ERROR')

    def test_strict_json_and_single_fenced_envelope(self):
        raw = '{"status":"PASS","findings":[]}'
        for text in [raw, '  '+raw+'  ', '```json\n'+raw+'\n```', '```\n'+raw+'\n```']:
            self.assertEqual(audit.parse_verdict_text(text), {'status':'PASS','findings':[]})
        for text in ['Explanation '+raw, raw+' trailing', '```json\n'+raw+'\n``` trailing',
                     '```json '+raw+'```', '```json\n{broken}\n```',
                     '```json\n'+raw+'\n```\n```json\n'+raw+'\n```', '[]',
                     '{"status":"REDO","status":"PASS","findings":[]}', '{"x":NaN}']:
            with self.assertRaises(ValueError):
                audit.parse_verdict_text(text)

    def test_failure_stages_never_expose_exception_text(self):
        self.complete.side_effect = TimeoutError('private provider payload')
        result = self.review()
        self.assertEqual(result['error']['stage'], 'provider_completion')
        self.assertNotIn('private provider payload', json.dumps(result))
        self.complete.side_effect = None
        self.complete.return_value = 'not valid JSON'
        self.assertEqual(self.review()['error']['stage'], 'parse_verdict')
        self.complete.return_value = '{"status":"PASS","findings":[{}]}'
        self.assertEqual(self.review()['error']['stage'], 'validate_verdict')
        self.load_policy.side_effect = FileNotFoundError('private authority path')
        self.assertEqual(self.review()['error']['stage'], 'load_policy')
        self.load_policy.side_effect = None
        self.complete.return_value = '{"status":"PASS","findings":[]}'
        self.cached_review.side_effect = RuntimeError('private connection data')
        self.assertEqual(self.review()['error']['stage'], 'cache_lookup')
        self.cached_review.side_effect = None
        self.persist_review.side_effect = OSError('private DB error')
        result = self.review()
        self.assertEqual(result['error']['stage'], 'persist_review')
        self.assertEqual(result['error']['type'], 'OSError')
        self.assertNotIn('private DB error', json.dumps(result))

    def test_fenced_response_does_not_weaken_citation_validation(self):
        self.complete.return_value = '```json\n'+json.dumps({'status':'REDO','findings':[
            {'rule':{'source':'manual','quote':'not present'},
             'evidence':{'source':'activity:0','quote':'not present'},'correction':'Fix it'}]})+'\n```'
        result = self.review()
        self.assertEqual(result['status'], 'ERROR')
        self.assertEqual(result['error']['stage'], 'validate_verdict')

    def test_missing_credentials_never_calls_provider(self):
        audit.config.CONCIERGE_API_KEY = ""
        with patch.object(reasoner.httpx, 'AsyncClient') as client:
            with self.assertRaises(ValueError):
                reasoner.complete([])
            client.assert_not_called()

    def stream_client(self, lines=None, heartbeat=False, read_error=False):
        state = {'response_closed':False, 'client_closed':False, 'cancelled':False}

        class Response:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                state['response_closed'] = True

            def raise_for_status(self):
                pass

            async def aiter_lines(self):
                if read_error:
                    raise reasoner.httpx.ReadTimeout('private transport details')
                if heartbeat:
                    try:
                        while True:
                            yield ': heartbeat'
                            await asyncio.sleep(0.002)
                    except asyncio.CancelledError:
                        state['cancelled'] = True
                        raise
                for line in lines or []:
                    yield line

        class Client:
            def __init__(self, **kwargs):
                state['timeout'] = kwargs['timeout']

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                state['client_closed'] = True

            def stream(self, *args, **kwargs):
                state['request'] = kwargs
                return Response()

        return Client, state

    def sse(self, delta=None, finish=None):
        return ['data: '+json.dumps({'choices':[{'index':0,'delta':delta or {},'finish_reason':finish}]}), '']

    def test_stream_assembles_content_excludes_reasoning_and_uses_deadlines(self):
        lines = [': heartbeat', ''] + self.sse({'role':'assistant'})
        lines += self.sse({'reasoning_content':'private reasoning'})
        lines += self.sse({'content':'final '}) + self.sse({'content':'answer'}, 'stop')
        lines += ['data: {"choices":[],"usage":{"completion_tokens":10}}', '', 'data: [DONE]', '']
        client, state = self.stream_client(lines)
        with patch.object(reasoner.httpx, 'AsyncClient', client):
            self.assertEqual(reasoner.complete([], True), 'final answer')
        self.assertTrue(state['request']['json']['stream'])
        self.assertEqual(state['request']['json']['response_format'], {'type':'json_object'})
        self.assertNotIn('thinking', state['request']['json'])
        self.assertEqual(state['timeout'].read, 0.1)
        self.assertEqual(state['timeout'].connect, 0.05)
        self.assertTrue(state['response_closed'] and state['client_closed'])

    def test_stream_multiline_sse_data(self):
        lines = ['data: {"choices": [', 'data: {"delta":{"content":"ok"},"finish_reason":"stop"}]}', '',
                 'data: [DONE]', '']
        client, state = self.stream_client(lines)
        with patch.object(reasoner.httpx, 'AsyncClient', client):
            self.assertEqual(reasoner.complete([]), 'ok')

    def test_stream_rejects_malformed_error_truncation_and_abnormal_finish(self):
        cases = [self.sse({'content':'partial'}),
                 self.sse({'content':'partial'}, 'length') + ['data: [DONE]', ''],
                 self.sse({}, 'stop') + ['data: [DONE]', ''],
                 ['data: [DONE]', ''], ['data: {broken}', ''],
                 ['data: {"error":{"message":"private"}}', ''],
                 ['event: error', 'data: {}', ''],
                 self.sse({'content':'ok'}, 'stop') + ['data: [DONE]']]
        for lines in cases:
            client, state = self.stream_client(lines)
            with patch.object(reasoner.httpx, 'AsyncClient', client):
                with self.assertRaises(ValueError):
                    reasoner.complete([])
            self.assertTrue(state['response_closed'] and state['client_closed'])

    def test_stream_hard_deadline_cancels_continuous_heartbeat(self):
        audit.config.REVIEW_TIMEOUT = 0.02
        client, state = self.stream_client(heartbeat=True)
        with patch.object(reasoner.httpx, 'AsyncClient', client):
            with self.assertRaises(TimeoutError):
                reasoner.complete([])
        self.assertTrue(state['cancelled'])
        self.assertTrue(state['response_closed'] and state['client_closed'])

    def test_stream_explicit_cancellation_closes_contexts(self):
        client, state = self.stream_client(heartbeat=True)

        async def cancel_request():
            task = asyncio.create_task(reasoner._complete_stream([]))
            await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        with patch.object(reasoner.httpx, 'AsyncClient', client):
            asyncio.run(cancel_request())
        self.assertTrue(state['cancelled'])
        self.assertTrue(state['response_closed'] and state['client_closed'])

    def test_stream_read_timeout_closes_contexts(self):
        client, state = self.stream_client(read_error=True)
        with patch.object(reasoner.httpx, 'AsyncClient', client):
            with self.assertRaises(reasoner.httpx.ReadTimeout):
                reasoner.complete([])
        self.assertTrue(state['response_closed'] and state['client_closed'])


if __name__ == '__main__':
    unittest.main()
