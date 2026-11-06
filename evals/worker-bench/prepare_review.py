#!/usr/bin/env python3
"""Export separate randomized reviewer packs; keep identity mapping outside packs."""
import argparse
import json
import pathlib
import secrets
import random
import sys

from bench import audit, read, sha, write

DIMENSIONS = ['事实与约束', '矛盾映射', '机制与差异', '创新归属', '可行性与否证', '报告证据与可读性']


def prepare(records, output, mapping, calibration=False):
    output, mapping = pathlib.Path(output).resolve(), pathlib.Path(mapping).resolve()
    if mapping == output or output in mapping.parents:
        raise ValueError('identity mapping must be outside the reviewer pack')
    if output.exists() or mapping.exists():
        raise ValueError('use new output and mapping paths; do not overwrite reviews')
    entries, identities = [], {}
    for record_path in records:
        record_path = pathlib.Path(record_path).resolve()
        run = record_path.parent
        result = audit(argparse.Namespace(run=run))
        if result['integrity'] != 'PASS' or result['status'] != 'completed_smoke':
            raise ValueError('incomplete or altered run: ' + str(record_path))
        if not calibration and not result['formal_eligible']:
            raise ValueError('formal pack rejects calibration/simulated/ineligible runs')
        record = read(record_path)
        from bench import safe_path
        body = safe_path(run, record['output_path']).read_bytes()
        # No run metadata or source paths are copied to the reviewer pack.
        anon = 'R-' + secrets.token_hex(6)
        entries.append((anon, body))
        identities[anon] = {'record': str(record_path), 'case_id': record['case_id'], 'arm': record['arm'],
                            'task_scope': record.get('task_scope', 'full'), 'input_sha256': record['input_sha256'],
                            'model': record['model'], 'skill_commit': record['skill_commit'],
                            'output_sha256': sha(body), 'condition_findings': result['condition_findings']}
    output.mkdir(parents=True)
    for reviewer in ('reviewer-1', 'reviewer-2'):
        folder = output / reviewer
        folder.mkdir()
        ordered = entries.copy()
        random.SystemRandom().shuffle(ordered)
        forms = []
        for anon, body in ordered:
            (folder / (anon + '.md')).write_bytes(body)
            forms.append({'id': anon, 'scores': [
                {'dimension': d, 'score': None, 'quote': '', 'rationale': ''} for d in DIMENSIONS],
                'critical_errors': [], 'guessed_arm': '', 'human_reviewer': None})
        write(folder / 'scorecards.json', {'purpose': 'calibration' if calibration else 'formal',
                                          'reviewer_id': reviewer, 'order': [x[0] for x in ordered],
                                          'reviews': forms})
    mapping.parent.mkdir(parents=True, exist_ok=True)
    write(mapping, {'purpose': 'calibration' if calibration else 'formal', 'mapping': identities})
    return {'count': len(entries), 'reviewer_packs': str(output), 'mapping': str(mapping),
            'purpose': 'calibration' if calibration else 'formal', 'scoring': 'pending_human_review',
            'note': 'Technical content preserved. Reviewer must record any inferred identity.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--records', nargs='+', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--mapping', required=True)
    p.add_argument('--calibration', action='store_true')
    args = p.parse_args()
    try:
        print(json.dumps(prepare(args.records, args.output, args.mapping, args.calibration),
                         ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
