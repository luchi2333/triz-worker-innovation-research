#!/usr/bin/env python3
"""Host-run evaluation collection. Does not call a model or grade engineering quality."""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BASELINE = '19e20f4a2b4d2d9e0b46a214fd609146be0a7d7c'
UNAVAILABLE = 'unavailable'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = pathlib.Path(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':')).encode('utf-8'))


def safe_path(run, name):
    run = pathlib.Path(run).resolve()
    path = (run / name).resolve()
    if path == run or run not in path.parents:
        raise ValueError('artifact path must stay inside the run directory')
    return path


def load_run(run):
    run = pathlib.Path(run).resolve()
    record = read(run / 'run-record.json')
    return run, record


def save(run, record):
    record['updated_at'] = now()
    write(run / 'run-record.json', record)


def artifact(run, record, name, content):
    path = safe_path(run, name)
    if path.exists():
        raise ValueError('refusing to overwrite original artifact: ' + name)
    path.write_bytes(content)
    record.setdefault('artifacts', {})[name] = sha(content)


def event(record, kind, **data):
    record.setdefault('events', []).append({'at': now(), 'kind': kind, **data})


def conditions(record):
    runtime = record['runtime']
    loaded = runtime.get('loaded_skills', [])
    triz = [s for s in loaded if 'triz' in json.dumps(s).lower()]
    reasons = []
    if record['arm'] in ('A', 'B') and triz:
        reasons.append('condition_violated: TRIZ Skill loaded in A/B')
    if runtime.get('skill_inventory_complete') is not True:
        reasons.append('unverified: incomplete loaded-Skill inventory')
    if record['arm'] == 'C0' and not any(
        isinstance(s, dict) and s.get('commit') == BASELINE for s in triz
    ):
        reasons.append('unverified: actual C0 baseline loading not attested')
    if record['arm'] == 'C1' and not any(
        isinstance(s, dict) and s.get('commit') == record.get('skill_commit') for s in triz
    ):
        reasons.append('unverified: actual C1 candidate loading not attested')
    if runtime.get('context_isolation') != 'isolated':
        reasons.append('formal_ineligible: session is not isolated')
    if runtime.get('execution_kind') != 'live_host':
        reasons.append('formal_ineligible: not attested as a live model execution')
    if runtime.get('model', UNAVAILABLE) == UNAVAILABLE:
        reasons.append('formal_ineligible: exact model version unavailable')
    if any(record['budget'].get(k, UNAVAILABLE) == UNAVAILABLE
           for k in ('seconds', 'search_calls', 'output_tokens')):
        reasons.append('formal_ineligible: budget not frozen')
    if any(x.get('mode') == 'simulated' for x in record['confirmation_transcript']):
        reasons.append('formal_ineligible: simulated confirmation; smoke calibration only')
    return reasons


def prepare(args):
    if bool(args.retry_of) != bool(args.retry_reason):
        raise ValueError('retry-of and retry-reason must be supplied together')
    candidate = getattr(args, 'candidate', None)
    scope = getattr(args, 'scope', 'full')
    if args.arm == 'C1':
        if not candidate or not re.fullmatch(r'[0-9a-f]{40}', candidate):
            raise ValueError('C1 requires a frozen full candidate commit SHA')
        if git('rev-parse', candidate + '^{commit}').decode().strip() != candidate:
            raise ValueError('candidate must resolve to the specified commit')
    elif candidate:
        raise ValueError('candidate commit applies only to C1')
    if scope != 'full' and args.arm not in ('C0', 'C1'):
        raise ValueError('research-brief scope is shared by C0/C1 only')
    run = pathlib.Path(args.output).resolve()
    if run.exists():
        raise ValueError('use a new output directory; previous attempts must be retained')
    case_path = HERE / 'cases' / (args.case + '.json')
    case = read(case_path)
    # Allowlist: no evaluator fields, confirmation text, or labels enter the prompt.
    visible = {k: case[k] for k in ('input', 'constraints')}
    runtime = read(args.runtime)
    if not isinstance(runtime.get('loaded_skills'), list):
        raise ValueError('runtime.loaded_skills must be an actual inventory array')
    record = read(HERE / 'run-record-template.json')
    budget = read(args.budget) if args.budget else {
        k: UNAVAILABLE for k in ('seconds', 'search_calls', 'output_tokens')}
    for key in ('seconds', 'search_calls', 'output_tokens'):
        value = budget.get(key, UNAVAILABLE)
        if value != UNAVAILABLE and (isinstance(value, bool)
                                     or not isinstance(value, (int, float)) or value < 0):
            raise ValueError('budget values must be nonnegative numbers or unavailable')
    run.mkdir(parents=True)
    record.update(run_id=run.name, case_id=args.case, arm=args.arm,
                  status='prepared', baseline_commit=BASELINE,
                  skill_commit=BASELINE if args.arm == 'C0' else candidate if args.arm == 'C1' else UNAVAILABLE,
                  task_scope=scope,
                  model=runtime.get('model', UNAVAILABLE), runtime=runtime,
                  loaded_skills=runtime['loaded_skills'],
                  tool_permissions=runtime.get('tool_permissions', []),
                  budget=budget, search_log=[], confirmation_transcript=[],
                  usage={k: UNAVAILABLE for k in ('seconds', 'input_tokens', 'output_tokens')},
                  started_at=now(), execution_segments=[], artifacts={},
                  retry_of=args.retry_of or UNAVAILABLE,
                  retry_reason=args.retry_reason or UNAVAILABLE,
                  evaluation_commit=git('rev-parse', 'HEAD').decode().strip(),
                  branch=git('branch', '--show-current').decode().strip())
    record['asset_sha256'] = {name: sha((HERE / name).read_bytes()) for name in (
        'bench.py', 'run-record-template.json', 'protocol.md', 'splits.json',
        'prompts/common.md', 'prompts/B.md')}
    record['confirmation_source_sha256'] = read(HERE / 'splits.json')['confirmation_source_sha256']
    record['tracked_working_tree_changes'] = git('status', '--porcelain', '--untracked-files=no').decode()
    write(run / 'case-input.json', visible)
    prompt = (HERE / 'prompts/common.md').read_text(encoding='utf-8')
    if args.arm == 'B':
        prompt += '\n' + (HERE / 'prompts/B.md').read_text(encoding='utf-8')
    if args.arm in ('C0', 'C1'):
        # Never inspect or export Skill content for A/B.
        prefix = 'triz-worker-innovation-research/'
        commit = record['skill_commit']
        folder = args.arm.lower() + '-skill'
        files = git('ls-tree', '-r', '--name-only', commit, '--', prefix).decode().splitlines()
        if not files or prefix + 'SKILL.md' not in files:
            raise ValueError('selected commit has no complete Skill package')
        record['baseline_resource_sha256'] = {}
        for name in files:
            body = git('show', commit + ':' + name)
            relative = name[len(prefix):]
            path = safe_path(run, folder + '/' + relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            record['baseline_resource_sha256'][relative] = sha(body)
        record['skill_resource_directory'] = folder
        prompt += '\n' + (run / folder / 'SKILL.md').read_text(encoding='utf-8')
        prompt += '\n参考资料仅从本次 ' + folder + ' 目录按阶段读取。\n'
    additions = []
    if scope == 'research-brief':
        additions.append('prompts/research-brief.md')
    if args.arm == 'C1':
        additions.append('prompts/C1-claim-review.md')
    for name in additions:
        body = (HERE / name).read_bytes()
        record['asset_sha256'][name] = sha(body)
        prompt += '\n' + body.decode('utf-8')
    prompt += '\n题面：\n' + json.dumps(visible, ensure_ascii=False, indent=2) + '\n'
    artifact(run, record, 'prompt.md', prompt.encode('utf-8'))
    record['prompt_sha256'] = sha(prompt.encode('utf-8'))
    record['input_sha256'] = digest(visible)
    record['case_file_sha256'] = sha(case_path.read_bytes())
    record['condition_findings'] = conditions(record)
    event(record, 'prepared', note='Prompt packaging only; no model execution claimed.')
    save(run, record)
    return {'status': record['status'], 'prompt': str(run / 'prompt.md'),
            'condition_findings': record['condition_findings']}


def collect(args):
    run, record = load_run(args.run)
    if record['status'] not in ('prepared', 'confirmed'):
        raise ValueError('output collection requires prepared or confirmed state')
    body = pathlib.Path(args.text).read_bytes()
    if not body.strip():
        raise ValueError('raw output cannot be empty')
    if args.action == 'request':
        if record['arm'] not in ('C0', 'C1') or record['status'] != 'prepared':
            raise ValueError('G1.5 request requires prepared C0/C1 state')
        name = 'direction-output.md'
        record['status'] = 'awaiting_confirmation'
        event(record, 'confirmation_requested', output=name, mode='host_collected')
    else:
        if record['arm'] in ('C0', 'C1') and record['status'] != 'confirmed':
            raise ValueError('C0/C1 cannot finish before a real or authorized simulated reply')
        name = 'final-output.md'
        record['status'] = 'completed_smoke'
        record['output_path'] = name
        event(record, 'output_collected', output=name,
              note='Collection complete; full Skill stage completion and engineering validity are separate.')
    artifact(run, record, name, body)
    save(run, record)
    return {'status': record['status'], 'artifact': str(run / name)}


def confirm(args):
    run, record = load_run(args.run)
    if record['status'] != 'awaiting_confirmation':
        raise ValueError('cannot release confirmation before an actual recorded request')
    if args.mode == 'simulated':
        authorization = record['runtime'].get('simulation_authorization')
        if not authorization:
            raise ValueError('simulated replies require recorded user authorization')
        # Delayed read: preset replies are never read by prepare().
        source = HERE / 'private/confirmations.json'
        if sha(source.read_bytes()) != record['confirmation_source_sha256']:
            raise ValueError('preset confirmation changed since protocol snapshot')
        reply = read(source)[record['case_id']]
    else:
        authorization = 'actual user reply supplied by host'
        reply = args.reply
        if not reply or not reply.strip():
            raise ValueError('human mode needs the actual reply text')
    entry = {'role': 'user_simulated' if args.mode == 'simulated' else 'user',
             'mode': args.mode, 'text': reply, 'at': now(),
             'authorization': authorization}
    record['confirmation_transcript'].append(entry)
    record['status'] = 'confirmed'
    event(record, 'confirmation_released', mode=args.mode)
    record['condition_findings'] = conditions(record)
    save(run, record)
    return entry


def telemetry(args):
    run, record = load_run(args.run)
    data = read(args.metadata)
    for key in ('seconds', 'input_tokens', 'output_tokens'):
        value = data.get(key, UNAVAILABLE)
        if value != UNAVAILABLE and (isinstance(value, bool)
                                     or not isinstance(value, (int, float)) or value < 0):
            raise ValueError('usage must be a nonnegative number or unavailable')
        record['usage'][key] = value
    record['usage']['scope'] = data.get('scope', UNAVAILABLE)
    event(record, 'telemetry_recorded', source=str(args.metadata))
    save(run, record)
    return record['usage']


def audit(args):
    run, record = load_run(args.run)
    errors = []
    required = set(read(HERE / 'run-record-template.json'))
    if not required.issubset(record):
        errors.append('missing template keys: ' + ', '.join(sorted(required - set(record))))
    for name, expected in record.get('artifacts', {}).items():
        path = safe_path(run, name)
        if not path.is_file() or sha(path.read_bytes()) != expected:
            errors.append('artifact missing or changed: ' + name)
    if digest(read(run / 'case-input.json')) != record['input_sha256']:
        errors.append('input hash mismatch')
    if record['prompt_sha256'] != record.get('artifacts', {}).get('prompt.md'):
        errors.append('prompt hash mismatch')
    for name, expected in record.get('baseline_resource_sha256', {}).items():
        path = safe_path(run, record.get('skill_resource_directory', 'c0-skill') + '/' + name)
        if not path.is_file() or sha(path.read_bytes()) != expected:
            errors.append('baseline resource missing or changed: ' + name)
    if record['status'] == 'completed_smoke' and record['arm'] in ('C0', 'C1'):
        if not record['confirmation_transcript']:
            errors.append('completed C0 has no confirmation')
        kinds = [e['kind'] for e in record['events']]
        if ('confirmation_requested' not in kinds or 'confirmation_released' not in kinds
                or kinds.index('confirmation_requested') > kinds.index('confirmation_released')):
            errors.append('confirmation event order invalid')
    findings = conditions(record)
    for metric, budget_key in [('seconds', 'seconds'), ('output_tokens', 'output_tokens')]:
        actual, limit = record['usage'].get(metric, UNAVAILABLE), record['budget'].get(budget_key, UNAVAILABLE)
        if isinstance(actual, (int, float)) and isinstance(limit, (int, float)) and actual > limit:
            findings.append('over_budget: ' + budget_key)
    search_limit = record['budget'].get('search_calls', UNAVAILABLE)
    attempts = sum(q.get('attempt_count', 1) for q in record.get('search_log', []))
    if isinstance(search_limit, (int, float)) and attempts > search_limit:
        findings.append('over_budget: search_calls')
    return {'integrity': 'FAIL' if errors else 'PASS', 'errors': errors,
            'condition_findings': findings,
            'formal_eligible': not errors and not findings and record['status'] == 'completed_smoke',
            'status': record['status'], 'grading': 'not_performed',
            'full_skill_completion': record.get('full_skill_completion', 'not_attested')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--case', required=True, choices=['S01', 'S02', 'S03', 'M01', 'M02', 'M03', 'E01', 'E02', 'P01', 'P02', 'P03'])
    p.add_argument('--arm', required=True, choices=['A', 'B', 'C0', 'C1'])
    p.add_argument('--candidate', help='C1 frozen full commit SHA; never exports dirty working files')
    p.add_argument('--scope', choices=['full', 'research-brief'], default='full')
    p.add_argument('--runtime', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--budget')
    p.add_argument('--retry-of')
    p.add_argument('--retry-reason')
    for name in ('request', 'finish'):
        p = sub.add_parser(name)
        p.add_argument('--run', required=True)
        p.add_argument('--text', required=True)
    p = sub.add_parser('confirm')
    p.add_argument('--run', required=True)
    p.add_argument('--mode', choices=['human', 'simulated'], required=True)
    p.add_argument('--reply')
    p = sub.add_parser('telemetry')
    p.add_argument('--run', required=True)
    p.add_argument('--metadata', required=True)
    p = sub.add_parser('audit')
    p.add_argument('--run', required=True)
    args = parser.parse_args()
    try:
        result = {'prepare': prepare, 'request': collect, 'finish': collect,
                  'confirm': confirm, 'telemetry': telemetry, 'audit': audit}[args.action](args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get('integrity') == 'FAIL' else 0
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
