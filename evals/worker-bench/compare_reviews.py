#!/usr/bin/env python3
"""Validate two real reviewer submissions and describe paired C0/C1 scores.

Does not generate scores, infer a causal benefit, or replace preregistered acceptance criteria.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys

from bench import read, sha
from prepare_review import DIMENSIONS


def compare(mapping_path, scorecard_paths):
    mapping_doc = read(mapping_path)
    mapping = mapping_doc['mapping']
    if len(scorecard_paths) != 2 or not mapping:
        raise ValueError('two reviewer submissions and a nonempty identity mapping are required')
    reviewers, submissions = [], []
    for path in map(Path, scorecard_paths):
        card = read(path)
        if card.get('purpose') != mapping_doc.get('purpose'):
            raise ValueError('formal and calibration reviews must not be mixed')
        entries, names = {}, set()
        for review in card['reviews']:
            rid = review['id']
            if rid not in mapping or rid in entries:
                raise ValueError('review IDs must uniquely match the blinded mapping')
            name = review.get('human_reviewer')
            if not isinstance(name, str) or not name.strip():
                raise ValueError('real human reviewer identity is required; no automatic scoring')
            names.add(name.strip())
            body = (path.parent / (rid+'.md')).read_bytes()
            if sha(body) != mapping[rid]['output_sha256']:
                raise ValueError('reviewed output changed since blinding')
            scores = {}
            for row in review['scores']:
                dim, score = row['dimension'], row['score']
                if dim not in DIMENSIONS or dim in scores or isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 4:
                    raise ValueError('scores must uniquely cover rubric dimensions with integers 0..4')
                if not row.get('quote') or not row.get('rationale'):
                    raise ValueError('scores need a quote or explicit missing location and a rationale')
                scores[dim] = score
            if set(scores) != set(DIMENSIONS):
                raise ValueError('missing rubric dimension')
            if not isinstance(review.get('critical_errors'), list):
                raise ValueError('critical_errors must be an explicit list')
            for error in review['critical_errors']:
                if not isinstance(error, dict) or not all(error.get(k) for k in ('quote', 'category', 'rationale')):
                    raise ValueError('critical errors need quote, category and rationale')
            entries[rid] = {'scores': scores, 'critical_errors': review['critical_errors'],
                            'guessed_arm': review.get('guessed_arm', '')}
        if set(entries) != set(mapping) or len(names) != 1:
            raise ValueError('each submission needs one identified reviewer and all mapped outputs')
        reviewers.append(next(iter(names)))
        submissions.append(entries)
    if reviewers[0] == reviewers[1]:
        raise ValueError('two distinct actual reviewers required')
    keyed, agreement = {}, []
    for rid, identity in mapping.items():
        key = (identity['case_id'], identity['model'], identity['arm'])
        if key in keyed:
            raise ValueError('duplicate case/model/arm; resolve repeats explicitly before comparison')
        first, second = [s[rid] for s in submissions]
        agreement.extend(abs(first['scores'][d]-second['scores'][d]) for d in DIMENSIONS)
        keyed[key] = {'scores': {d: statistics.mean([first['scores'][d], second['scores'][d]]) for d in DIMENSIONS},
                      'reviewer_scores': [first['scores'], second['scores']],
                      'guessed_arms': [first['guessed_arm'], second['guessed_arm']],
                      'task_scope': identity.get('task_scope', 'full'),
                      'input_sha256': identity.get('input_sha256', 'unavailable'),
                      'critical_errors': [first['critical_errors'], second['critical_errors']],
                      'output_sha256': identity['output_sha256']}
    paired, unpaired = [], []
    for case, model in sorted({key[:2] for key in keyed}):
        if (case, model, 'C0') not in keyed or (case, model, 'C1') not in keyed:
            unpaired.append({'case_id': case, 'model': model})
            continue
        c0, c1 = keyed[(case, model, 'C0')], keyed[(case, model, 'C1')]
        if c0['task_scope'] != c1['task_scope'] or c0['input_sha256'] != c1['input_sha256']:
            raise ValueError('paired outputs must share task scope and frozen input')
        paired.append({'case_id': case, 'model': model,
                       'delta_by_dimension': {d: c1['scores'][d]-c0['scores'][d] for d in DIMENSIONS},
                       'C0': c0, 'C1': c1})
    return {'purpose': mapping_doc['purpose'], 'reviewers': reviewers, 'paired_count': len(paired),
            'pairs': paired, 'unpaired': unpaired,
            'mean_delta_by_dimension': {d: statistics.mean([p['delta_by_dimension'][d] for p in paired]) if paired else 'unavailable' for d in DIMENSIONS},
            'agreement_within_one_point': statistics.mean([v <= 1 for v in agreement]),
            'acceptance_decision': 'not_inferred',
            'scope': 'Descriptive paired scores, all recorded critical errors retained. Identity fields do not prove reviewer independence; preregistered design and costs must be assessed separately.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping', type=Path, required=True)
    parser.add_argument('--scorecards', type=Path, nargs=2, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('use a new output file')
        result = compare(args.mapping, args.scorecards)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
