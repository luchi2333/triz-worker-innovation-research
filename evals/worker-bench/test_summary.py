import pathlib
import tempfile
import unittest

from bench import write
from summarize_results import summarize


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)

    def record(self, name, usage=None, replay=False):
        path = self.root / (name + '.json')
        write(path, {'run_id': name, 'case_id': 'S01', 'arm': 'C0', 'status': 'draft',
                     'runtime': {'execution_kind': 'artifact_replay' if replay else 'live_host'},
                     'usage': usage or {}})
        return path

    def test_unknown_is_not_zero(self):
        result = summarize([self.record('one', {'seconds': 3}), self.record('two')])
        self.assertEqual(result['usage']['seconds']['known_subtotal'], 3)
        self.assertEqual(result['usage']['seconds']['total'], 'unavailable')
        self.assertEqual(result['usage']['input_tokens']['unavailable_runs'], 2)
        self.assertEqual(result['effectiveness_conclusion'], 'not_evaluated')

    def test_replay_does_not_double_count_model_usage(self):
        result = summarize([self.record('one', {'seconds': 3}),
                            self.record('replay', {'seconds': 3}, True)])
        self.assertEqual(result['usage']['seconds']['known_subtotal'], 3)
        self.assertEqual(result['replay_count'], 1)
        self.assertEqual(result['logical_case_arm_count'], 1)

    def test_duplicate_run_is_rejected(self):
        path = self.record('same')
        with self.assertRaises(ValueError):
            summarize([path, path])

    def test_invalid_cost_is_rejected(self):
        for value in (-1, True, float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                summarize([self.record('bad', {'seconds': value})])


if __name__ == '__main__':
    unittest.main()
