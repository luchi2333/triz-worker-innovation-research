#!/usr/bin/env python3
"""Summarize collected runs without converting unavailable metadata into zero."""
import argparse
import collections
import json
import math
import pathlib
import sys

from bench import audit, read, write


def summarize(paths):
    runs, seen = [], set()
    for path in paths:
        path = pathlib.Path(path).resolve()
        record = read(path)
        run_id = record.get('run_id')
        if not run_id or run_id in seen:
            raise ValueError('missing or duplicate run_id: ' + str(run_id))
        seen.add(run_id)
        if 'artifacts' in record and 'runtime' in record:
            checked = audit(argparse.Namespace(run=path.parent))
        else:
            checked = {'integrity': 'not_checked_legacy', 'formal_eligible': False,
                       'condition_findings': ['legacy run requires explicit integrity review']}
        row = {k: record.get(k, 'unavailable') for k in ('run_id', 'case_id', 'arm', 'status')}
        row.update(integrity=checked['integrity'], formal_eligible=checked['formal_eligible'],
                   condition_findings=checked['condition_findings'], usage={}, record=str(path))
        for key in ('seconds', 'input_tokens', 'output_tokens'):
            value = record.get('usage', {}).get(key, 'unavailable')
            if value is None:
                value = 'unavailable'
            if value != 'unavailable' and (isinstance(value, bool) or not isinstance(value, (int, float))
                                          or not math.isfinite(value) or value < 0):
                raise ValueError('invalid usage ' + key + ' in ' + run_id)
            row['usage'][key] = value
        row['usage_scope'] = record.get('usage', {}).get('scope', record.get('usage', {}).get('seconds_scope', 'unavailable'))
        row['execution_kind'] = record.get('runtime', {}).get('execution_kind', 'legacy_host_run')
        row['continuation_of'] = record.get('continuation_of', 'unavailable')
        runs.append(row)
    totals = {}
    # Replays never add historical model cost a second time.
    cost_runs = [r for r in runs if r['execution_kind'] != 'artifact_replay']
    for key in ('seconds', 'input_tokens', 'output_tokens'):
        known = [r['usage'][key] for r in cost_runs if r['usage'][key] != 'unavailable']
        totals[key] = {'known_subtotal': sum(known), 'known_runs': len(known),
                       'unavailable_runs': len(cost_runs) - len(known),
                       'total': sum(known) if len(known) == len(cost_runs) and cost_runs else 'unavailable'}
    return {'run_count': len(runs),
            'logical_case_arm_count': len({(r['case_id'], r['arm']) for r in runs}),
            'formal_eligible_count': sum(r['formal_eligible'] for r in runs),
            'replay_count': sum(r['execution_kind'] == 'artifact_replay' for r in runs),
            'status_counts': dict(collections.Counter(r['status'] for r in runs)),
            'usage': totals, 'runs': runs, 'scores': 'unavailable',
            'effectiveness_conclusion': 'not_evaluated',
            'scope': 'Known costs retain their recorded measurement boundaries; partial seconds are not end-to-end latency.'}


def markdown(result):
    lines = ['# M0 运行汇总', '',
             f"运行记录 {result['run_count']}；题目/组别组合 {result['logical_case_arm_count']}；正式条件合格 {result['formal_eligible_count']}；回放 {result['replay_count']}。", '',
             '| 运行 | 题号/组 | 状态 | 完整性 | 正式条件 |', '|---|---|---|---|---|']
    for r in result['runs']:
        lines.append(f"| {r['run_id']} | {r['case_id']}/{r['arm']} | {r['status']} | {r['integrity']} | {r['formal_eligible']} |")
    lines += ['', '未取得的 token 保留 unavailable；回放不重复计入历史模型成本。部分计时只按各记录口径解释。', '',
              '没有独立评分，尚不能计算或声称质量改善。', '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--records', nargs='+', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    try:
        result = summarize(args.records)
        out = pathlib.Path(args.output)
        if out.exists():
            raise ValueError('use a new output directory to preserve previous summaries')
        out.mkdir(parents=True)
        write(out / 'summary.json', result)
        (out / 'summary.md').write_text(markdown(result), encoding='utf-8')
        print(json.dumps({'run_count': result['run_count'], 'output': str(out),
                          'effectiveness_conclusion': result['effectiveness_conclusion']}, ensure_ascii=False))
        return 0
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
