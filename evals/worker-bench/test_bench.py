"""Negative-path tests for evaluation integrity; no model or web calls."""
import argparse
import pathlib
import tempfile
import unittest

import bench
import prepare_review


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.runtime = self.root / 'runtime.json'
        self.runtime_data = {
            'model': 'test-fixture-model', 'context_isolation': 'isolated',
            'skill_inventory_complete': True,
            'loaded_skills': [{'name': 'triz-worker-innovation-research', 'commit': bench.BASELINE}],
            'simulation_authorization': 'test fixture authorization only'}
        bench.write(self.runtime, self.runtime_data)
        self.run = self.root / 'run'
        self.text = self.root / 'output.md'
        self.text.write_text('Fixture output. Not an engineering result.', encoding='utf-8')

    def prepare(self, arm='C0', budget=None):
        return bench.prepare(argparse.Namespace(case='S01', arm=arm, runtime=self.runtime,
                             output=self.run, budget=budget, retry_of=None, retry_reason=None))

    def request(self):
        return bench.collect(argparse.Namespace(action='request', run=self.run, text=self.text))

    def confirm(self):
        return bench.confirm(argparse.Namespace(run=self.run, mode='simulated', reply=None))

    def finish(self):
        return bench.collect(argparse.Namespace(action='finish', run=self.run, text=self.text))

    def test_prepare_does_not_leak_confirmation(self):
        self.prepare()
        prompt = (self.run / 'prompt.md').read_text()
        self.assertNotIn('比较限力和改接触面。', prompt)
        self.assertEqual(set(bench.read(self.run / 'case-input.json')), {'input', 'constraints'})
        self.assertEqual(bench.audit(argparse.Namespace(run=self.run))['integrity'], 'PASS')

    def test_cannot_confirm_or_finish_before_request(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.confirm()
        with self.assertRaises(ValueError):
            self.finish()

    def test_simulation_requires_explicit_authorization(self):
        del self.runtime_data['simulation_authorization']
        bench.write(self.runtime, self.runtime_data)
        self.prepare()
        self.request()
        with self.assertRaises(ValueError):
            self.confirm()

    def test_changed_confirmation_source_is_rejected(self):
        self.prepare()
        self.request()
        record = bench.read(self.run / 'run-record.json')
        record['confirmation_source_sha256'] = '0' * 64
        bench.write(self.run / 'run-record.json', record)
        with self.assertRaisesRegex(ValueError, 'confirmation changed'):
            self.confirm()

    def test_simulated_run_is_not_formal_evidence(self):
        self.prepare()
        self.request()
        reply = self.confirm()
        self.assertEqual(reply['role'], 'user_simulated')
        self.finish()
        report = bench.audit(argparse.Namespace(run=self.run))
        self.assertEqual(report['integrity'], 'PASS')
        self.assertFalse(report['formal_eligible'])
        self.assertTrue(any('simulated' in x for x in report['condition_findings']))

    def test_ab_contamination_retained_and_flagged(self):
        self.prepare('A')
        self.assertFalse((self.run / 'c0-skill').exists())
        self.finish()
        report = bench.audit(argparse.Namespace(run=self.run))
        self.assertTrue(any('condition_violated' in x for x in report['condition_findings']))
        self.assertEqual(report['integrity'], 'PASS')

    def test_attested_human_path_is_not_rejected_as_simulation(self):
        self.runtime_data['execution_kind'] = 'live_host'
        bench.write(self.runtime, self.runtime_data)
        budget = self.root / 'budget.json'
        bench.write(budget, {'seconds': 100, 'search_calls': 5, 'output_tokens': 1000})
        self.prepare('C0', budget)
        self.request()
        bench.confirm(argparse.Namespace(run=self.run, mode='human', reply='Test user reply'))
        self.finish()
        report = bench.audit(argparse.Namespace(run=self.run))
        self.assertEqual(report['integrity'], 'PASS')
        self.assertTrue(report['formal_eligible'])
        self.assertEqual(report['grading'], 'not_performed')
        self.assertEqual(report['full_skill_completion'], 'not_attested')

    def test_case_migration_preserves_original_inputs_and_splits(self):
        original = __import__('json').loads(bench.git(
            'show', '5d39400108b049a4a6855ebf1786564c8d099def:evals/worker-bench/cases.json'))
        migrated = bench.read(bench.HERE / 'cases.json')
        splits = bench.read(bench.HERE / 'splits.json')
        for group in ('development', 'smoke'):
            self.assertEqual([x['id'] for x in original[group]], [x['id'] for x in migrated[group]])
            for old in original[group]:
                new = bench.read(bench.HERE / 'cases' / (old['id'] + '.json'))
                self.assertEqual(new, {k: old[k] for k in ('id', 'input', 'constraints')})
                self.assertNotIn('confirmation', new)
            for row in splits[group]:
                self.assertEqual(bench.sha((bench.HERE / row['path']).read_bytes()), row['sha256'])
        self.assertEqual(splits['holdout_total'], 4)

    def test_baseline_tamper_is_detected(self):
        self.prepare()
        (self.run / 'c0-skill/SKILL.md').write_text('changed', encoding='utf-8')
        report = bench.audit(argparse.Namespace(run=self.run))
        self.assertEqual(report['integrity'], 'FAIL')

    def test_output_tamper_is_detected(self):
        self.prepare('B')
        self.finish()
        (self.run / 'final-output.md').write_text('changed', encoding='utf-8')
        self.assertEqual(bench.audit(argparse.Namespace(run=self.run))['integrity'], 'FAIL')

    def test_refuses_to_overwrite_original_attempt(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.prepare()
        self.request()
        with self.assertRaises(ValueError):
            self.request()

    def test_budget_overrun_preserves_result(self):
        budget = self.root / 'budget.json'
        bench.write(budget, {'seconds': 1, 'search_calls': 0, 'output_tokens': 1})
        self.prepare('B', budget)
        self.finish()
        meta = self.root / 'usage.json'
        bench.write(meta, {'seconds': 2, 'input_tokens': 'unavailable', 'output_tokens': 2})
        bench.telemetry(argparse.Namespace(run=self.run, metadata=meta))
        report = bench.audit(argparse.Namespace(run=self.run))
        self.assertIn('over_budget: seconds', report['condition_findings'])
        self.assertIn('over_budget: output_tokens', report['condition_findings'])
        self.assertTrue((self.run / 'final-output.md').exists())

    def test_review_pack_rejects_ineligible_formal_run(self):
        self.prepare()
        self.request()
        self.confirm()
        self.finish()
        with self.assertRaises(ValueError):
            prepare_review.prepare([self.run / 'run-record.json'], self.root / 'review',
                                   self.root / 'private/mapping.json')
        output = self.root / 'calibration'
        prepare_review.prepare([self.run / 'run-record.json'], output,
                               self.root / 'private/mapping.json', True)
        self.assertFalse((output / 'mapping.json').exists())
        cards = bench.read(output / 'reviewer-1/scorecards.json')
        self.assertEqual(cards['purpose'], 'calibration')
        self.assertIsNone(cards['reviews'][0]['scores'][0]['score'])

    def test_review_mapping_cannot_be_inside_pack(self):
        with self.assertRaises(ValueError):
            prepare_review.prepare([], self.root / 'review', self.root / 'review/mapping.json', True)

    def test_path_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            bench.safe_path(self.run, '../outside.md')

    def test_c1_requires_frozen_commit_and_preserves_confirmation_gate(self):
        args = argparse.Namespace(case='S01', arm='C1', runtime=self.runtime,
                                  output=self.run, budget=None, retry_of=None, retry_reason=None,
                                  candidate=None, scope='research-brief')
        with self.assertRaisesRegex(ValueError, 'frozen full'):
            bench.prepare(args)
        args.candidate = bench.BASELINE  # Historical export fixture, no effectiveness comparison.
        bench.prepare(args)
        self.assertTrue((self.run / 'c1-skill/SKILL.md').is_file())
        self.assertFalse((self.run / 'c0-skill').exists())
        record = bench.read(self.run / 'run-record.json')
        self.assertEqual(record['task_scope'], 'research-brief')
        self.assertIn('prompts/C1-claim-review.md', record['asset_sha256'])
        with self.assertRaises(ValueError):
            self.finish()
        self.request(); self.confirm(); self.finish()
        self.assertEqual(bench.audit(argparse.Namespace(run=self.run))['integrity'], 'PASS')
        path = self.run / 'c1-skill/SKILL.md'
        path.write_text('modified', encoding='utf-8')
        self.assertEqual(bench.audit(argparse.Namespace(run=self.run))['integrity'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
