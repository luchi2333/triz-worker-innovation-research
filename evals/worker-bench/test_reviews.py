"""Reviewer aggregation tests use conspicuously synthetic scores, not evaluation results."""
import copy
from pathlib import Path
import tempfile
import unittest

from bench import sha, write
from compare_reviews import compare
from prepare_review import DIMENSIONS


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        body = b'SYNTHETIC TEST FIXTURE ONLY'
        mapping = {'purpose': 'calibration', 'mapping': {
            rid: {'case_id': 'fixture', 'model': 'fixture-model', 'arm': arm, 'output_sha256': sha(body)}
            for rid, arm in [('x1', 'C0'), ('x2', 'C1')]}}
        self.mapping = self.root/'mapping.json'; write(self.mapping, mapping)
        self.cards = []
        for i in range(2):
            folder = self.root/str(i); folder.mkdir()
            for rid in mapping['mapping']:
                (folder/(rid+'.md')).write_bytes(body)
            card = {'purpose': 'calibration', 'reviews': [
                {'id': rid, 'human_reviewer': 'fixture reviewer '+str(i), 'critical_errors': [],
                 'scores': [{'dimension': d, 'score': 2, 'quote': 'fixture', 'rationale': 'fixture only'} for d in DIMENSIONS]}
                for rid in mapping['mapping']]}
            path = folder/'scorecards.json'; write(path, card)
            self.cards.append(path)

    def test_paired_descriptions_do_not_declare_effectiveness(self):
        result = compare(self.mapping, self.cards)
        self.assertEqual(result['paired_count'], 1)
        self.assertTrue(all(v == 0 for v in result['mean_delta_by_dimension'].values()))
        self.assertEqual(result['acceptance_decision'], 'not_inferred')

    def test_missing_or_automatic_reviews_rejected(self):
        from bench import read
        card = read(self.cards[0]); card['reviews'][0]['human_reviewer'] = None
        write(self.cards[0], card)
        with self.assertRaises(ValueError):
            compare(self.mapping, self.cards)

    def test_scores_and_reviewed_output_integrity(self):
        from bench import read
        card = read(self.cards[0]); card['reviews'][0]['scores'][0]['score'] = True
        write(self.cards[0], card)
        with self.assertRaises(ValueError):
            compare(self.mapping, self.cards)
        card['reviews'][0]['scores'][0]['score'] = 2; write(self.cards[0], card)
        (self.cards[0].parent/'x1.md').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            compare(self.mapping, self.cards)


if __name__ == '__main__':
    unittest.main()
