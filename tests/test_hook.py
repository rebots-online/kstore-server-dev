import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))
import kstore_turn_hook as hook
from kstore_client import KStoreClient, _sha256


class HookTests(unittest.TestCase):
    def test_catalog_links_actual_tools_without_treating_quoted_names_as_calls(self):
        client = Mock()
        client.pg_rows.return_value = [
            ('1', json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': [
                {'type': 'tool_use', 'id': 'call-stats', 'name': 'mcp__kstore__kstore_stats', 'input': {}}]}})),
            ('2', json.dumps({'type': 'user', 'message': {'role': 'user', 'content': [
                {'type': 'tool_result', 'tool_use_id': 'call-stats', 'content': 'green'}]}})),
            ('3', json.dumps({'type': 'assistant', 'message': {'content': [
                {'type': 'text', 'text': 'A quoted mcp__memory__write is not a call'}]}})),
            ('4', json.dumps({'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'exec_command', 'call_id': 'c'}})),
            ('5', json.dumps({'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'c', 'output': 'done'}})),
        ]
        catalog = hook.activity_catalog(client, 'stream', 1, 5)
        self.assertEqual(len(catalog), 5)
        self.assertEqual(catalog[0]['blocks'][0]['id'], catalog[1]['blocks'][0]['tool_use_id'])
        self.assertEqual(catalog[0]['source'], 'activity:1')
        self.assertNotIn('mcp__memory__write', json.dumps(catalog))
        self.assertEqual(catalog[2]['text_characters'], len('A quoted mcp__memory__write is not a call'))
        self.assertEqual(catalog[3]['call_id'], catalog[4]['call_id'])

    def test_stop_reviews_delayed_final_records_before_pass(self):
        client = Mock()
        client.pg_rows.return_value = []
        client.review.return_value = {'status': 'PASS'}
        initial = {'stream_id': 's', 'last_sequence': 5}
        final = {'stream_id': 's', 'last_sequence': 8}
        with patch.object(hook, 'archive', side_effect=[final, final]), patch.object(hook, 'git_evidence', return_value={}):
            receipt, verdict = hook.review_until_stable(client, None, {}, 'claude', initial, 2)
        self.assertEqual(verdict['status'], 'PASS')
        self.assertEqual(receipt['last_sequence'], 8)
        self.assertEqual([c.args[2] for c in client.review.call_args_list], [5, 8])
        self.assertEqual(client.review.call_args.args[3]['capture_event_count'], 7)

    def test_stop_continuous_activity_never_uses_stale_pass(self):
        client = Mock()
        client.pg_rows.return_value = []
        client.review.return_value = {'status': 'PASS'}
        initial = {'stream_id': 's', 'last_sequence': 0}
        tails = [{'stream_id': 's', 'last_sequence': n} for n in (1, 2, 3)]
        with patch.object(hook, 'archive', side_effect=tails), patch.object(hook, 'git_evidence', return_value={}):
            _, verdict = hook.review_until_stable(client, None, {}, 'claude', initial, 0)
        self.assertEqual(hook.stop_output(verdict)['decision'], 'block')
        self.assertEqual(client.review.call_count, 3)

    def test_startup_before_transcript_and_later_loss(self):
        for runtime in ('claude', 'codex'):
            with self.subTest(runtime=runtime), TemporaryDirectory(dir=Path(__file__).parent) as folder:
                state = Path(folder)
                transcript = state / 'not-yet-created.jsonl'
                payload = {'transcript_path': str(transcript), 'session_id': 'startup',
                           'hook_event_name': 'UserPromptSubmit', 'prompt': 'initial request'}
                client = Mock()
                first = hook.archive(client, state, payload, runtime)
                self.assertEqual(first['lines'], 0)
                self.assertEqual(first['new_events'], 1)
                self.assertIn('initial request', client.capture.call_args.args[1][0]['raw'])
                self.assertEqual(hook.archive(client, state, payload, runtime)['new_events'], 0)
                entry = ({'type': 'user', 'message': {'content': 'initial request'}}
                         if runtime == 'claude' else
                         {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user',
                          'content': [{'type': 'input_text', 'text': 'initial request'}]}})
                transcript.write_text(json.dumps(entry) + '\n')
                second = hook.archive(client, state, payload, runtime)
                self.assertEqual(second['stream_id'], first['stream_id'])
                self.assertEqual(second['new_events'], 1)
                self.assertEqual(second['last_sequence'], 1)
                transcript.unlink()
                with self.assertRaises(ValueError):
                    hook.archive(client, state, payload, runtime)

    def test_missing_stop_transcript_is_not_a_successful_capture(self):
        for runtime in ('claude', 'codex'):
            with self.subTest(runtime=runtime), TemporaryDirectory(dir=Path(__file__).parent) as folder:
                state = Path(folder)
                payload = {'transcript_path': str(state / 'absent.jsonl'),
                           'session_id': 'stop', 'hook_event_name': 'Stop'}
                with self.assertRaises(FileNotFoundError):
                    hook.archive(Mock(), state, payload, runtime)

    def test_pre_emits_context_after_durable_startup_capture(self):
        for runtime in ('claude', 'codex'):
            with self.subTest(runtime=runtime), TemporaryDirectory(dir=Path(__file__).parent) as folder:
                client = Mock()
                client.receipt_root = Path(folder) / 'receipts'
                client.inject.return_value = {'context': 'authoritative context'}
                payload = {'transcript_path': str(Path(folder) / 'absent.jsonl'),
                           'session_id': 'pre-startup', 'hook_event_name': 'UserPromptSubmit',
                           'prompt': 'initial request'}
                output = io.StringIO()
                with patch.object(hook, 'KStoreClient', return_value=client), \
                     patch.object(sys, 'argv', ['hook', 'pre', runtime]), \
                     patch.object(sys, 'stdin', io.StringIO(json.dumps(payload))), \
                     patch.object(sys, 'stdout', output):
                    self.assertEqual(hook.main(), 0)
                result = json.loads(output.getvalue())['hookSpecificOutput']
                self.assertEqual(result['hookEventName'], 'UserPromptSubmit')
                self.assertIn('authoritative context', result['additionalContext'])
                self.assertEqual(client.mock_calls[0][0], 'capture')
                self.assertEqual(client.mock_calls[1][0], 'inject')
                self.assertEqual(client.inject.call_args.args, ('initial request',))
                receipts = list((client.receipt_root / runtime).glob('*.json'))
                self.assertEqual(len(receipts), 1)
                self.assertEqual(json.loads(receipts[0].read_text())['last_sequence'], 0)

    def test_duplicate_receipt_reports_observed_entity_count(self):
        client = object.__new__(KStoreClient)
        client.pg_rows = Mock(return_value=[('document', '2', _sha256('body'), _sha256('body'), '12')])
        receipt = client.verify_stored('doc', 'markdown', 'body')
        self.assertEqual(receipt['postgres_entities'], 12)
        self.assertTrue(receipt['byte_exact_readback'])

    def test_codex_calls_outputs_are_not_private_analysis(self):
        for kind in ('function_call', 'function_call_output', 'custom_tool_call', 'custom_tool_call_output'):
            entry = {'type': 'response_item', 'payload': {'type': kind, 'channel': 'analysis', 'arguments': 'git push', 'output': 'rejected'}}
            raw = json.dumps(entry)
            self.assertEqual(hook.eligible(entry, raw)['raw'], raw)

    def test_private_reasoning_excluded(self):
        for payload in ({'type': 'reasoning'}, {'type': 'message', 'channel': 'analysis'}):
            entry = {'type': 'response_item', 'payload': payload}
            self.assertIsNone(hook.eligible(entry, json.dumps(entry)))

    def test_claude_mixed_blocks_keeps_tools_and_results(self):
        entry = {'type': 'assistant', 'message': {'content': [
            {'type': 'thinking', 'thinking': 'private'}, {'type': 'text', 'text': 'visible'},
            {'type': 'tool_use', 'id': 'a', 'input': {'cmd': 'git status'}},
            {'type': 'tool_result', 'tool_use_id': 'a', 'content': 'dirty'}]}}
        result = hook.eligible(entry, json.dumps(entry))
        self.assertTrue(result['filtered'])
        self.assertNotIn('private', result['raw'])
        self.assertIn('git status', result['raw'])
        self.assertIn('dirty', result['raw'])

    def test_unknown_error_activity_kept(self):
        raw = '{ "type": "new_runtime_error", "error": "failed" }'
        self.assertEqual(hook.eligible(json.loads(raw), raw)['raw'], raw)

    def test_stop_blocks_error_and_redo_but_pass_allows(self):
        for status in ('REDO', 'ERROR', 'unknown'):
            self.assertEqual(hook.stop_output({'status': status})['decision'], 'block')
        self.assertEqual(hook.stop_output({'status': 'PASS'}), {})

    def test_capture_retry_and_partial_line(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            state = Path(folder)
            transcript = state / 'transcript.jsonl'
            raw = json.dumps({'type': 'response_item', 'payload': {'type': 'function_call', 'name': 'exec_command', 'arguments': 'git status'}})
            transcript.write_text(raw + '\n{"partial":')
            payload = {'transcript_path': str(transcript), 'session_id': 'unit-session'}
            client = Mock()
            receipt = hook.archive(client, state, payload, 'codex')
            self.assertEqual(receipt['new_events'], 1)
            self.assertEqual(client.capture.call_args.args[1][0]['raw'], raw)
            self.assertEqual(hook.archive(client, state, payload, 'codex')['new_events'], 0)
            transcript.write_text(raw + '\n' + json.dumps({'type': 'error', 'message': 'failure'}) + '\n')
            self.assertEqual(hook.archive(client, state, payload, 'codex')['new_events'], 1)
            transcript.write_text(raw.replace('git status', 'git push') + '\n')
            with self.assertRaises(ValueError):
                hook.archive(client, state, payload, 'codex')

    def test_failed_capture_retains_outbox_and_cursor(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            state = Path(folder)
            transcript = state / 'input.jsonl'
            transcript.write_text('{"type":"user","message":{"content":"hello"}}\n')
            payload = {'transcript_path': str(transcript), 'session_id': 'failure'}
            client = Mock()
            client.capture.side_effect = RuntimeError('database unavailable')
            with self.assertRaises(RuntimeError):
                hook.archive(client, state, payload, 'claude')
            self.assertEqual(len(list(state.glob('*.outbox.json'))), 1)
            client.capture.side_effect = None
            self.assertEqual(hook.archive(client, state, payload, 'claude')['new_events'], 0)
            self.assertEqual(len(list(state.glob('*.outbox.json'))), 0)


    def run_stop_hook(self, client, payload, clock=None):
        output = io.StringIO()
        with patch.object(hook, 'KStoreClient', return_value=client), \
             patch.object(hook, 'git_evidence', return_value={}), \
             patch.object(hook, 'time', clock or Mock()), \
             patch.object(sys, 'argv', ['hook', 'post', 'claude']), \
             patch.object(sys, 'stdin', io.StringIO(json.dumps(payload))), \
             patch.object(sys, 'stdout', output):
            rc = hook.main()
        return rc, output.getvalue()

    @staticmethod
    def append_lines(transcript, entries):
        with transcript.open('a') as handle:
            handle.write(''.join(json.dumps(entry, ensure_ascii=False) + '\n' for entry in entries))

    @staticmethod
    def stop_payload(transcript, last_message):
        return {'hook_event_name': 'Stop', 'transcript_path': str(transcript),
                'session_id': 'settle-tests', 'last_assistant_message': last_message}

    @staticmethod
    def captured(client):
        events = []
        for captured_call in client.capture.call_args_list:
            events.extend(captured_call.args[1])
        return events

    def test_settle_returns_after_two_unchanged_polls(self):
        with patch.object(hook, 'archive', return_value={'last_sequence': 5}) as archive_mock, \
             patch.object(hook, 'time') as clock:
            receipt = hook.settle_before_review(Mock(), None, {}, 'claude', {'last_sequence': 5})
        self.assertEqual(receipt['last_sequence'], 5)
        self.assertEqual(archive_mock.call_count, 2)
        clock.sleep.assert_has_calls([call(0.2), call(0.2)])
        self.assertEqual(clock.sleep.call_count, 2)

    def test_settle_bounds_at_three_polls_when_activity_keeps_growing(self):
        growth = [{'last_sequence': n} for n in (6, 7, 8)]
        with patch.object(hook, 'archive', side_effect=growth) as archive_mock, \
             patch.object(hook, 'time') as clock:
            receipt = hook.settle_before_review(Mock(), None, {}, 'claude', {'last_sequence': 5})
        self.assertEqual(receipt['last_sequence'], 8)
        self.assertEqual(archive_mock.call_count, 3)
        clock.sleep.assert_has_calls([call(0.2)] * 3)
        self.assertEqual(clock.sleep.call_count, 3)

    def test_settle_propagates_capture_failure(self):
        with patch.object(hook, 'archive', side_effect=RuntimeError('capture unavailable')), \
             patch.object(hook, 'time') as clock:
            with self.assertRaises(RuntimeError):
                hook.settle_before_review(Mock(), None, {}, 'claude', {'last_sequence': 0})
        clock.sleep.assert_called_once_with(0.2)

    def test_settled_late_final_gets_exactly_one_complete_review(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            state_root, transcript = Path(folder), Path(folder) / 'native.jsonl'
            self.append_lines(transcript, [
                {'type': 'user', 'message': {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'Ship the verified fix'}]}}])
            client = Mock()
            client.receipt_root = state_root
            client.pg_rows.return_value = []
            client.review.return_value = {'status': 'PASS'}
            clock = Mock()

            def flush_final(seconds):
                if clock.sleep.call_count == 1:
                    self.append_lines(transcript, [{'type': 'assistant', 'message': {
                        'role': 'assistant', 'content': 'Done: pushed release'}}])
            clock.sleep.side_effect = flush_final
            rc, out = self.run_stop_hook(client, self.stop_payload(transcript, 'working'), clock)
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out), {})
            self.assertEqual(client.review.call_count, 1)
            self.assertEqual(client.review.call_args.args[1:3], (0, 2))
            self.assertEqual(client.review.call_args.args[3]['capture_event_count'], 3)
            clock.sleep.assert_has_calls([call(0.2)] * 3)
            self.assertEqual(clock.sleep.call_count, 3)
            self.assertEqual([e['sequence'] for e in self.captured(client)], [0, 1, 2])
            review = json.loads(next((state_root / 'claude').glob('*.review.json')).read_text())
            self.assertEqual(review['status'], 'PASS')

    def test_late_events_after_review_start_still_trigger_rereview(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            state_root, transcript = Path(folder), Path(folder) / 'native.jsonl'
            self.append_lines(transcript, [
                {'type': 'user', 'message': {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'Ship the verified fix'}]}}])
            client = Mock()
            client.receipt_root = state_root
            client.pg_rows.return_value = []

            def review_and_flush(stream_id, first, last, evidence):
                if client.review.call_count == 1:
                    self.append_lines(transcript, [{'type': 'assistant', 'message': {
                        'role': 'assistant', 'content': 'Flushed after review started'}}])
                return {'status': 'PASS'}
            client.review.side_effect = review_and_flush
            rc, out = self.run_stop_hook(client, self.stop_payload(transcript, 'working'), Mock())
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out), {})
            self.assertEqual([c.args[2] for c in client.review.call_args_list], [1, 2])
            self.assertEqual([e['sequence'] for e in self.captured(client)], [0, 1, 2])

    def test_bound_exhaustion_still_enters_stable_review_guard(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            state_root, transcript = Path(folder), Path(folder) / 'native.jsonl'
            self.append_lines(transcript, [
                {'type': 'user', 'message': {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'Ship the verified fix'}]}}])
            client = Mock()
            client.receipt_root = state_root
            client.pg_rows.return_value = []
            client.review.return_value = {'status': 'PASS'}
            clock = Mock()

            def flush_each_poll(seconds):
                self.append_lines(transcript, [{'type': 'assistant', 'message': {
                    'role': 'assistant', 'content': f'late {clock.sleep.call_count}'}}])
            clock.sleep.side_effect = flush_each_poll
            rc, out = self.run_stop_hook(client, self.stop_payload(transcript, 'working'), clock)
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out), {})
            self.assertEqual(clock.sleep.call_count, 3)
            self.assertEqual(client.review.call_count, 1)
            self.assertEqual(client.review.call_args.args[1:3], (0, 4))
            self.assertEqual([e['sequence'] for e in self.captured(client)], [0, 1, 2, 3, 4])

    def test_provider_error_still_refuses_completion_after_settling(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            state_root, transcript = Path(folder), Path(folder) / 'native.jsonl'
            self.append_lines(transcript, [
                {'type': 'user', 'message': {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'Ship the verified fix'}]}}])
            client = Mock()
            client.receipt_root = state_root
            client.pg_rows.return_value = []
            client.review.return_value = {'status': 'ERROR', 'error': {
                'type': 'ReadTimeout', 'stage': 'provider_completion'}}
            clock = Mock()
            rc, out = self.run_stop_hook(client, self.stop_payload(transcript, 'working'), clock)
            self.assertEqual(rc, 0)
            decision = json.loads(out)
            self.assertEqual(decision['decision'], 'block')
            self.assertIn('ReadTimeout', decision['reason'])
            self.assertEqual(client.review.call_count, 1)
            self.assertEqual(clock.sleep.call_count, 2)
            review = json.loads(next((state_root / 'claude').glob('*.review.json')).read_text())
            self.assertEqual(review['status'], 'ERROR')
            cursors = [path for path in (state_root / 'claude').glob('*.json')
                       if not path.name.endswith('.review.json')]
            self.assertEqual(json.loads(cursors[0].read_text())['review_from'], 0)

    def test_two_blocked_cycles_capture_each_eligible_line_once_without_reasoning(self):
        with TemporaryDirectory(dir=Path(__file__).parent) as folder:
            state_root, transcript = Path(folder), Path(folder) / 'native.jsonl'
            self.append_lines(transcript, [
                {'type': 'user', 'message': {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'Ship the verified fix'}]}},
                {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
                    {'type': 'thinking', 'thinking': 'private scratch'}]}},
                {'type': 'assistant', 'message': {'role': 'assistant', 'content': [
                    {'type': 'text', 'text': 'Implemented and tested'}]}},
            ])
            cycle1 = Mock()
            cycle1.receipt_root = state_root
            cycle1.pg_rows.return_value = []
            cycle1.review.return_value = {'status': 'ERROR', 'error': {
                'type': 'ReadTimeout', 'stage': 'provider_completion'}}
            clock1 = Mock()

            def flush_final(seconds):
                if clock1.sleep.call_count == 1:
                    self.append_lines(transcript, [{'type': 'assistant', 'message': {
                        'role': 'assistant', 'content': 'Done: pushed release'}}])
            clock1.sleep.side_effect = flush_final
            rc1, out1 = self.run_stop_hook(cycle1, self.stop_payload(
                transcript, 'Implemented and tested'), clock1)
            self.assertEqual(rc1, 0)
            self.assertEqual(json.loads(out1)['decision'], 'block')
            self.assertEqual(cycle1.review.call_count, 1)
            self.assertEqual(cycle1.review.call_args.args[1:3], (0, 3))

            self.append_lines(transcript, [
                {'type': 'user', 'message': {'role': 'user', 'content': [
                    {'type': 'text', 'text': 'KStore post failed; repair and retry'}]}},
                {'type': 'hook_blocking_error', 'payload': {'source': 'Stop', 'error': 'blocked'}},
                {'type': 'stop_hook_summary', 'payload': {'decision': 'block'}},
            ])
            cycle2 = Mock()
            cycle2.receipt_root = state_root
            cycle2.pg_rows.return_value = []
            cycle2.review.return_value = {'status': 'PASS'}
            rc2, out2 = self.run_stop_hook(cycle2, self.stop_payload(
                transcript, 'Done: pushed release'), Mock())
            self.assertEqual(rc2, 0)
            self.assertEqual(json.loads(out2), {})
            self.assertEqual(cycle2.review.call_count, 1)
            self.assertEqual(cycle2.review.call_args.args[1:3], (0, 7))

            events = self.captured(cycle1) + self.captured(cycle2)
            self.assertEqual(sorted(e['sequence'] for e in events), list(range(8)))
            raws = [e['raw'] for e in events]
            self.assertFalse(any('private scratch' in raw for raw in raws))
            self.assertTrue(any('Done: pushed release' in raw for raw in raws))
            self.assertTrue(any('stop_hook_summary' in raw for raw in raws))


if __name__ == '__main__':
    unittest.main()
