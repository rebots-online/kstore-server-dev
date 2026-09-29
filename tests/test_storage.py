"""Storage transaction boundaries and evidence invariants, without network services."""
import hashlib
import unittest
from unittest.mock import MagicMock, patch

from kstore import activity, storage
from kstore.db import SCHEMA


class StorageTests(unittest.TestCase):
    def connection(self, responses):
        conn, cur = MagicMock(), MagicMock()
        conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cur
        cur.fetchone.side_effect = responses
        return conn, cur

    def test_capture_commits_queue_on_same_cursor_without_embedding(self):
        conn, cur = self.connection([None, (1,)])
        with patch.object(storage, 'pg', return_value=conn), patch('kstore.db.qdrant', side_effect=AssertionError('inline vector call')):
            result = storage.store_document('a.txt', 'literal\ntext', 'docs')
        sql = [call.args[0] for call in cur.execute.call_args_list]
        self.assertTrue(any('document_revisions' in s and s.startswith('INSERT') for s in sql))
        self.assertTrue(any('INSERT INTO entities' in s for s in sql))
        self.assertTrue(any('INSERT INTO embedding_jobs' in s for s in sql))
        self.assertEqual(sql[0], 'SET LOCAL synchronous_commit = on')
        self.assertEqual(result['indexing'], 'pending')
        self.assertEqual(result['sha256'], hashlib.sha256(b'literal\ntext').hexdigest())
        self.assertTrue(result['stored'])
        conn.__exit__.assert_called_once_with(None, None, None)

    def test_capture_database_error_propagates_and_rolls_back(self):
        conn, cur = self.connection([None])
        def execute(sql, params=None):
            if 'INSERT INTO embedding_jobs' in sql:
                raise RuntimeError('queue unavailable')
        cur.execute.side_effect = execute
        with patch.object(storage, 'pg', return_value=conn):
            with self.assertRaisesRegex(RuntimeError, 'queue unavailable'):
                storage.store_document('a.txt', 'text', 'docs')
        self.assertIs(conn.__exit__.call_args.args[0], RuntimeError)
        conn.commit.assert_not_called()

    def test_unchanged_document_preserves_revision_and_completed_queue(self):
        digest = hashlib.sha256(b'text').hexdigest()
        conn, cur = self.connection([('00000000-0000-0000-0000-000000000001', digest, 7), (0,)])
        cur.fetchall.return_value = [('00000000-0000-0000-0000-000000000002',)]
        with patch.object(storage, 'pg', return_value=conn):
            result = storage.store_document('a.txt', 'text', 'docs')
        self.assertTrue(result['duplicate'])
        self.assertEqual(result['revision'], 7)
        self.assertEqual(result['indexing'], 'complete')
        sql = '\n'.join(call.args[0] for call in cur.execute.call_args_list)
        self.assertNotIn('INSERT INTO document_revisions', sql)
        self.assertNotIn('DELETE', sql)
        self.assertIn('ON CONFLICT DO NOTHING', sql)

    def test_changed_document_appends_revision(self):
        conn, cur = self.connection([('00000000-0000-0000-0000-000000000001', 'old-hash', 7), (1,)])
        with patch.object(storage, 'pg', return_value=conn):
            result = storage.store_document('a.txt', 'new', 'docs')
        self.assertEqual(result['revision'], 8)
        sql = '\n'.join(call.args[0] for call in cur.execute.call_args_list)
        self.assertNotIn('DELETE', sql)
        self.assertIn('INSERT INTO document_revisions', sql)

    def test_activity_prevalidation_rejects_invalid_batch_without_db(self):
        bad_batches = [
            [{'sequence': -1, 'raw': '{}'}],
            [{'sequence': True, 'raw': '{}'}],
            [{'sequence': 1, 'raw': '{}'}, {'sequence': 1, 'raw': '{}'}],
            [{'sequence': 2, 'raw': '{}'}, {'sequence': 0, 'raw': '{}'}],
            [{'sequence': 0, 'raw': 'bad\x00'}],
            [{'sequence': 0, 'raw': {}}],
            [{'sequence': 0, 'raw': '{}', 'filtered': 'false'}],
        ]
        with patch.object(activity, 'pg') as pg:
            for events in bad_batches:
                with self.subTest(events=events), self.assertRaises(ValueError):
                    activity.store_activity('session', events)
            pg.assert_not_called()

    def test_activity_duplicate_succeeds_without_new_document(self):
        raw = '{"x": "雪"}\n'
        digest = hashlib.sha256(raw.encode()).hexdigest()
        conn, cur = self.connection([(digest,)])
        with patch.object(activity, 'pg', return_value=conn), patch.object(activity, '_store_document') as store:
            result = activity.store_activity('session', [{'sequence': 2, 'raw': raw}])
        store.assert_not_called()
        self.assertEqual(result['events'], [{'sequence': 2, 'sha256': digest}])

    def test_activity_conflict_rolls_back_entire_batch(self):
        conn, cur = self.connection([None, ('different-hash',)])
        with patch.object(activity, 'pg', return_value=conn), patch.object(activity, '_store_document') as store:
            with self.assertRaisesRegex(ValueError, 'conflicts'):
                activity.store_activity('session', [{'sequence': 1, 'raw': '{}'}, {'sequence': 2, 'raw': '[]'}])
        store.assert_called_once()
        self.assertIs(store.call_args.args[0], cur)
        self.assertIs(conn.__exit__.call_args.args[0], ValueError)

    def test_activity_exact_utf8_bytes_and_shared_transaction(self):
        raw = '{"x": "雪"}\n'
        conn, cur = self.connection([None])
        with patch.object(activity, 'pg', return_value=conn), patch.object(activity, '_store_document') as store:
            activity.store_activity('session', [{'sequence': 9, 'raw': raw, 'kind': 'tool_output'}])
        inserts = [c for c in cur.execute.call_args_list if 'INSERT INTO activity_events' in c.args[0]]
        self.assertEqual(inserts[0].args[1][3], raw.encode('utf-8'))
        self.assertIs(store.call_args.args[0], cur)
        self.assertEqual(store.call_args.args[2], raw)
        conn.__exit__.assert_called_once_with(None, None, None)

    def test_activity_queue_error_rolls_back_event(self):
        conn, cur = self.connection([None])
        with patch.object(activity, 'pg', return_value=conn), patch.object(activity, '_store_document', side_effect=RuntimeError('queue failed')):
            with self.assertRaises(RuntimeError):
                activity.store_activity('session', [{'sequence': 1, 'raw': '{}'}])
        self.assertIs(conn.__exit__.call_args.args[0], RuntimeError)

    def test_commit_failure_never_returns_success(self):
        conn, cur = self.connection([None, (1,)])
        conn.__exit__.side_effect = RuntimeError('commit connection lost')
        with patch.object(storage, 'pg', return_value=conn):
            with self.assertRaisesRegex(RuntimeError, 'commit connection lost'):
                storage.store_document('a.txt', 'text', 'docs')

    def test_activity_readback_retains_exact_bytes_and_metadata(self):
        raw = '{"x": "雪"}\n'
        conn, cur = self.connection([])
        digest = hashlib.sha256(raw.encode()).hexdigest()
        cur.fetchall.return_value = [(3, 'tool_result', memoryview(raw.encode()), digest, 'turn', True)]
        with patch.object(activity, 'pg', return_value=conn):
            rows = activity.activity_rows('session', 0, 5)
        self.assertEqual(rows[0]['raw'], raw)
        self.assertEqual(rows[0]['sha256'], digest)
        self.assertTrue(rows[0]['filtered'])
        self.assertIn('ORDER BY sequence', cur.execute.call_args.args[0])

    def test_oversized_json_is_bounded_without_truncation(self):
        content = '{"result":"' + '雪🙂a' * 4500 + '"}'
        conn, cur = self.connection([None, (5,)])
        with patch.object(storage, 'pg', return_value=conn):
            receipt = storage.store_document('activity/session/1', content, 'activity')
        inserts = [c.args[1] for c in cur.execute.call_args_list if 'INSERT INTO entities(' in c.args[0]]
        self.assertGreater(len(inserts), 1)
        self.assertTrue(all(0 < len(row[8]) <= 3000 for row in inserts))
        self.assertEqual(''.join(row[8] for row in inserts), content)
        self.assertEqual([row[6] for row in inserts], list(range(len(inserts))))
        self.assertEqual(receipt['chunks'], len(inserts))
        revision = [c.args[1] for c in cur.execute.call_args_list if 'INSERT INTO document_revisions' in c.args[0]]
        self.assertEqual(revision[0][2], content)
        self.assertEqual(revision[0][3], hashlib.sha256(content.encode()).hexdigest())
        self.assertTrue(all(row[7] == hashlib.sha256(row[8].encode()).hexdigest() for row in inserts))

    def test_schema_adds_durable_jobs_and_activity(self):
        self.assertIn('CREATE TABLE IF NOT EXISTS embedding_jobs', SCHEMA)
        self.assertIn('PRIMARY KEY(entity_uuid, model, collection)', SCHEMA)
        self.assertIn('raw BYTEA NOT NULL', SCHEMA)
        self.assertIn('PRIMARY KEY(stream_id, sequence)', SCHEMA)


if __name__ == '__main__':
    unittest.main()
