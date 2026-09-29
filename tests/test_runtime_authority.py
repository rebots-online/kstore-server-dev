import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'client'))
from runtime_authority import runtime_authority_context

RULE = {'id': 'task-list', 'path': 'DOCS/TOOLING_CONVENTIONS/conversation-task-list.md',
        'sha256': 'e3b0c44298fc1c149afbf4c8996fb924'}
REMINDER_TEXT = 'Use a TASK LIST sidebar; update it each turn.'


def authority_response(**overrides):
    response = {
        'context': 'KStore operator-authorized behavioural reminders.\n'
                   'Authority revision: rev-one\n\n'
                   + json.dumps(RULE, ensure_ascii=False) + '\n' + REMINDER_TEXT,
        'authority_revision': 'rev-one',
        'authority_rules': [dict(RULE)],
        'hits': 0,
    }
    response.update(overrides)
    return response


class RuntimeAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.inject.return_value = authority_response()
        self.policy_text = 'Adapter policy: capture every turn; never forge trust.'
        self.policy_path = '/home/robin/.claude/hooks/POLICY.md'

    def call(self, prompt='unrelated arithmetic, no policy keywords'):
        return runtime_authority_context(self.client, prompt,
                                         self.policy_text, self.policy_path)

    def test_unrelated_prompt_still_calls_inject_verbatim(self):
        prompt = 'what is 2+2?'
        result = self.call(prompt)
        self.client.inject.assert_called_once_with(prompt)
        self.assertIn(self.policy_text, result)
        self.assertIn(REMINDER_TEXT, result)

    def test_policy_and_reminder_text_survive_with_labels(self):
        result = self.call()
        self.assertIn(self.policy_path, result)
        self.assertIn('rev-one', result)
        self.assertIn(self.policy_text + '\n\nInjected manifest authority', result)
        self.assertIn(REMINDER_TEXT, result)
        self.assertIn(self.client.inject.return_value['context'], result)

    def test_revision_and_rule_descriptors_present(self):
        result = self.call()
        descriptors = json.dumps([RULE], sort_keys=True, ensure_ascii=False)
        self.assertIn('Rule descriptors: ' + descriptors, result)
        for value in RULE.values():
            self.assertIn(value, result)

    def test_changed_response_immediately_changes_result(self):
        first = self.call()
        self.assertIn('rev-one', first)
        self.assertIn(REMINDER_TEXT, first)
        changed_rule = dict(RULE, sha256='ff25d4c9c0b7b9c0a3f1d2e3f4a5b6c7')
        self.client.inject.return_value = authority_response(
            context='Changed operator correction: quote sources in reviews.',
            authority_revision='rev-two', authority_rules=[changed_rule])
        second = self.call()
        self.assertNotEqual(first, second)
        self.assertIn('rev-two', second)
        self.assertNotIn('rev-one', second)
        self.assertIn('Changed operator correction: quote sources in reviews.', second)
        self.assertNotIn(REMINDER_TEXT, second)
        self.assertIn(changed_rule['sha256'], second)

    def test_malformed_authority_fails(self):
        malformed = [
            None, [], 'text', {},
            authority_response(context=''), authority_response(context=None),
            authority_response(context=7),
            authority_response(authority_revision=''),
            authority_response(authority_revision=None),
            authority_response(authority_rules=[]),
            authority_response(authority_rules={}),
            authority_response(authority_rules=['rule']),
            authority_response(authority_rules=[{}]),
            authority_response(authority_rules=[dict(RULE, id='')]),
            authority_response(authority_rules=[dict(RULE, sha256='')]),
            authority_response(authority_rules=[{'id': 'a', 'path': 'p'}]),
            authority_response(authority_rules=[{'id': 5, 'path': 'p', 'sha256': 's'}]),
            authority_response(authority_rules=[dict(RULE, extra=object())]),
        ]
        for response in malformed:
            self.client.inject.reset_mock(return_value=True)
            self.client.inject.return_value = response
            with self.assertRaises(ValueError):
                runtime_authority_context(self.client, 'any prompt',
                                          self.policy_text, self.policy_path)
            self.client.inject.assert_called_once()

    def test_policy_inputs_required_before_delivery(self):
        for policy_text, policy_path in (('', self.policy_path),
                                         ('   ', self.policy_path),
                                         (self.policy_text, ''),
                                         (self.policy_text, '\t ')):
            self.client.inject.reset_mock()
            with self.assertRaises(ValueError):
                runtime_authority_context(self.client, 'any prompt',
                                          policy_text, policy_path)
            self.client.inject.assert_not_called()

    def test_transport_failure_is_not_fabricated_success(self):
        self.client.inject.side_effect = OSError('connection refused')
        with self.assertRaises(OSError):
            self.call()

    def test_composition_is_deterministic(self):
        self.assertEqual(self.call(), self.call())


if __name__ == '__main__':
    unittest.main()
