import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kstore.reminders import load_reminders

class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rule = self.root / "rule.md"
        self.rule.write_text("Use a TASK LIST sidebar.")
        self.manifest = self.root / "manifest.json"
        self.write([{"id":"task-list", "path":"rule.md"}])
    def write(self, rules):
        self.manifest.write_text(json.dumps({"schema":1,"rules":rules}))
    def test_revision_tracks_bytes_and_preserves_content(self):
        a = load_reminders(self.manifest,self.root)
        self.assertIn(self.rule.read_text(),a["context"])
        self.assertEqual(a,load_reminders(self.manifest,self.root))
        self.rule.write_text("Changed operator correction.")
        self.assertNotEqual(a["revision"],load_reminders(self.manifest,self.root)["revision"])
    def test_missing_empty_and_invalid(self):
        with self.assertRaises(ValueError):load_reminders(None,self.root)
        for body in (b"",b"\xff"):
            self.rule.write_bytes(body)
            with self.assertRaises(ValueError):load_reminders(self.manifest,self.root)
        self.rule.unlink()
        with self.assertRaises(OSError):load_reminders(self.manifest,self.root)
    def test_escape_duplicate_and_schema(self):
        for rules in ([{"id":"a","path":"../outside"}], [{"id":"a","path":"/etc/passwd"}],
                      [{"id":"a","path":"rule.md"},{"id":"a","path":"rule.md"}]):
            self.write(rules)
            with self.assertRaises(ValueError):load_reminders(self.manifest,self.root)
        self.manifest.write_text('{}')
        with self.assertRaises(ValueError):load_reminders(self.manifest,self.root)
    def test_symlink_escape(self):
        (self.root/'escape').symlink_to('/etc/passwd')
        self.write([{"id":"a","path":"escape"}])
        with self.assertRaises(ValueError):load_reminders(self.manifest,self.root)
    def test_unrelated_prompt_still_receives_authority(self):
        from kstore import concierge
        with patch.object(concierge.config,'REMINDER_MANIFEST',self.manifest), patch.object(concierge.config,'AUTHORITY_ROOT',self.root), patch.object(concierge,'_search_all',return_value=[]):
            response=concierge.inject(concierge.InjectRequest(prompt='unrelated arithmetic'))
            self.assertIn('TASK LIST',response.context)
            self.assertEqual(response.hits,0)
            self.assertEqual(response.authority_rules[0]['id'],'task-list')
            self.assertTrue(response.authority_revision)
    def test_authority_failure_does_not_silently_pass(self):
        from kstore import concierge
        from fastapi import HTTPException
        with patch.object(concierge.config,'REMINDER_MANIFEST',None):
            with self.assertRaises(HTTPException) as raised:concierge.inject(concierge.InjectRequest(prompt='hello'))
            self.assertEqual(raised.exception.status_code,503)
