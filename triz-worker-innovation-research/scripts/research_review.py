"""Optional, record-owned review aids. Structural checks never certify source semantics.

python scripts/research_review.py --record research-record.json --draft review-draft.json
python scripts/research_review.py --record research-record.json
Drafts are scaffolds: no reviewer decisions, measurements or matrix cells are invented.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
POLICIES = {'off', 'focused', 'complete'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def empty_review():
    return {'policy': 'off', 'claim_ids': [], 'mapping_cards': [], 'claim_checks': [],
            'experiment_designs': []}


def claim_basis(record, claim):
    return fingerprint({'claim': claim,
                        'sources': [s for s in record.get('sources', []) if s.get('id') in claim.get('supporting_source_ids', []) + claim.get('opposing_source_ids', [])],
                        'tests': [t for t in record.get('models_and_tests', {}).get('tests', []) if t.get('id') in claim.get('test_ids', [])]})


def mapping_cards(record):
    """Candidates come from bundled guidance; explicit selection remains an engineering decision."""
    guidance = json.loads((ROOT / 'references/parameter-guidance.json').read_text(encoding='utf-8'))
    cards = []
    for contradiction in record.get('contradictions', []):
        candidates = {}
        for side, field in [('improving', 'useful_result'), ('worsening', 'worsened_result')]:
            text = str(contradiction.get(field, ''))
            candidates[side] = [
                {'id': p['id'], 'name': p['zh'], 'matched_terms': matches,
                 'definition': p['definition_zh'], 'distinguish': p.get('confusable', [])}
                for p in guidance['parameters']
                if (matches := [term for term in p['field_terms'] if term in text])]
        cards.append({'contradiction_id': contradiction['id'],
                      'basis_sha256': fingerprint(contradiction),
                      'control_variable_id': contradiction.get('control_variable_id'),
                      'change_direction': contradiction.get('change_direction'),
                      'useful_result': contradiction.get('useful_result'),
                      'worsened_result': contradiction.get('worsened_result'),
                      'causality_basis': contradiction.get('causality_basis'),
                      'reverse_case': contradiction.get('ec2_reverse_case'),
                      'eligibility': contradiction.get('eligibility'),
                      'candidates': candidates, 'review_status': 'pending',
                      'selection_rationale': '', 'discriminating_observation': ''})
    return cards


def draft_review(record, claim_ids):
    claims = {c['id']: c for c in record.get('claims', [])}
    if not claim_ids or len(claim_ids) > 3 or not set(claim_ids) <= claims.keys():
        raise ValueError('focused draft needs one to three existing claim IDs')
    review = empty_review()
    review.update(policy='focused', claim_ids=claim_ids, mapping_cards=mapping_cards(record))
    for cid in claim_ids:
        review['claim_checks'].append({
            'id': cid, 'claim_id': cid, 'basis_sha256': claim_basis(record, claims[cid]),
            'status': 'pending', 'source_ids': [], 'test_ids': [],
            'support_scope': '', 'unsupported_scope': '', 'rationale': '',
            'action': 'pending', 'reviewer': '', 'review_mode': 'serial',
            'reviewed_at': ''})
    return review


def _audit_review(record, require_ready=False):
    review = record.get('quality_review')
    if review is None or review == empty_review() or (isinstance(review, dict) and review.get('policy') == 'off'):
        return {'status': 'NOT_CHECKED', 'errors': [], 'pending': [],
                'scope': 'Optional review disabled; existing evidence and safety contracts still apply.'}
    errors, pending = [], []
    if not isinstance(review, dict) or review.get('policy') not in POLICIES:
        raise ValueError('quality_review.policy must be off, focused or complete')
    claims = {c['id']: c for c in record.get('claims', [])}
    sources = {s['id']: s for s in record.get('sources', [])}
    tests = {t['id']: t for t in record.get('models_and_tests', {}).get('tests', [])}
    contradictions = {c['id']: c for c in record.get('contradictions', [])}
    scope = review.get('claim_ids', [])
    if not isinstance(scope, list) or not scope or len(scope) != len(set(scope)) or not set(scope) <= claims.keys():
        errors.append('quality_review needs unique existing claim_ids')
        scope = []
    if review['policy'] == 'focused' and len(scope) > 3:
        errors.append('focused review covers at most three decision-changing claims')
    if review['policy'] == 'complete' and set(scope) != claims.keys():
        errors.append('complete review must cover every recorded claim')
    checks = review.get('claim_checks', [])
    seen = set()
    for check in checks:
        cid = check.get('claim_id')
        if check.get('id') != cid:
            errors.append('claim check id must reuse claim_id for stable report references')
        if cid not in scope or cid in seen:
            errors.append('claim check must uniquely belong to review scope')
            continue
        seen.add(cid)
        claim = claims[cid]
        if check.get('basis_sha256') != claim_basis(record, claim):
            errors.append(f'{cid}: stale claim review; re-read the edited claim')
        status = check.get('status')
        if status == 'pending':
            pending.append(f'{cid}: claim support review pending')
            continue
        if status not in {'supported', 'partial', 'unsupported', 'unverifiable', 'hypothesis'}:
            errors.append(f'{cid}: invalid support status')
        action = check.get('action')
        if action not in {'retain', 'qualify', 'remove', 'pending'}:
            errors.append(f'{cid}: invalid review action')
        if action == 'pending':
            pending.append(f'{cid}: wording correction pending')
        if status in {'partial', 'unsupported', 'unverifiable'} and action == 'retain':
            errors.append(f'{cid}: unsupported scope cannot be retained unchanged')
        if status in {'partial', 'unsupported', 'unverifiable'} and action == 'qualify':
            pending.append(f'{cid}: revise claim then re-review its final wording and evidence')
        if status == 'hypothesis' and claim.get('evidence_status') != 'H':
            errors.append(f'{cid}: hypothesis review requires H evidence status')
        if status == 'hypothesis' and not all(claim.get(k) for k in ('allowed_wording', 'conditions', 'next_validation')):
            errors.append(f'{cid}: H needs bounded wording, conditions and next validation')
        if not all(str(check.get(k, '')).strip() for k in ('rationale', 'reviewer', 'reviewed_at')):
            errors.append(f'{cid}: completed review needs rationale, reviewer and date')
        if check.get('review_mode') not in {'serial', 'independent'}:
            errors.append(f'{cid}: review_mode must identify serial or independent review')
        source_ids, test_ids = check.get('source_ids', []), check.get('test_ids', [])
        if not set(source_ids) <= sources.keys() or not set(source_ids) <= set(claim.get('supporting_source_ids', [])):
            errors.append(f'{cid}: support sources must resolve and belong to the claim')
        if not set(test_ids) <= tests.keys() or not set(test_ids) <= set(claim.get('test_ids', [])):
            errors.append(f'{cid}: support tests must resolve and belong to the claim')
        if status == 'supported':
            if not check.get('support_scope'):
                errors.append(f'{cid}: supported claim needs the exact supported scope')
            if claim.get('evidence_status') == 'S' and not source_ids:
                errors.append(f'{cid}: S support needs a source locator and scope')
            if claim.get('evidence_status') == 'M' and (not test_ids or any(tests[t].get('status') != 'completed' for t in test_ids if t in tests)):
                errors.append(f'{cid}: M support requires completed test references; raw data checked by core contract')
            if claim.get('evidence_status') == 'H':
                errors.append(f'{cid}: H must remain hypothesis, not supported performance')
        if status in {'partial', 'unsupported', 'unverifiable'} and not check.get('unsupported_scope'):
            errors.append(f'{cid}: record the unsupported portion of the claim')
        if action == 'remove':
            pending.append(f'{cid}: remove from report and review scope, retaining history in run log')
    for cid in set(scope) - seen:
        pending.append(f'{cid}: missing claim check')
    cards = review.get('mapping_cards', [])
    seen_cards = set()
    guidance = json.loads((ROOT / 'references/parameter-guidance.json').read_text(encoding='utf-8'))
    parameter_names = {p['id']: p['zh'] for p in guidance['parameters']}
    for card in cards:
        cid = card.get('contradiction_id')
        if cid not in contradictions or cid in seen_cards:
            errors.append('mapping cards require unique existing contradiction IDs')
            continue
        seen_cards.add(cid)
        if card.get('basis_sha256') != fingerprint(contradictions[cid]):
            errors.append(f'{cid}: stale mapping card')
        for card_key, record_key in [('control_variable_id','control_variable_id'), ('change_direction','change_direction'),
                                     ('useful_result','useful_result'), ('worsened_result','worsened_result'),
                                     ('causality_basis','causality_basis'), ('reverse_case','ec2_reverse_case'), ('eligibility','eligibility')]:
            if card.get(card_key) != contradictions[cid].get(record_key):
                errors.append(f'{cid}: mapping card differs from recorded contradiction: {card_key}')
        for side in ('improving', 'worsening'):
            candidates = card.get('candidates', {}).get(side, [])
            if not isinstance(candidates, list) or any(isinstance(c.get('id'), bool) or c.get('name') != parameter_names.get(c.get('id')) or c.get('id') not in parameter_names for c in candidates):
                errors.append(f'{cid}: mapping candidates require canonical parameter IDs and names')
        if card.get('review_status') == 'pending':
            pending.append(f'{cid}: mapping card pending')
        elif card.get('review_status') != 'reviewed' or not all(card.get(k) for k in ('selection_rationale', 'discriminating_observation')):
            errors.append(f'{cid}: mapping card needs rationale and discriminating observation')
    if review['policy'] == 'complete' and seen_cards != contradictions.keys():
        pending.append('complete review needs all contradiction mapping cards')
    protocols = {p['id']: p for p in record.get('models_and_tests', {}).get('protocols', [])}
    seen_designs = set()
    for design in review.get('experiment_designs', []):
        pid = design.get('protocol_id')
        if pid not in protocols or pid in seen_designs:
            errors.append('experiment design must reference a unique existing protocol')
            continue
        seen_designs.add(pid)
        if design.get('basis_sha256') != fingerprint(protocols[pid]):
            errors.append(f'{pid}: stale experiment design')
        if design.get('status') == 'planned':
            pending.append(f'{pid}: design planned; measurements or decisions missing')
        elif design.get('status') == 'ready':
            for key in ('sample_unit', 'baseline', 'allocation_order', 'measurement_chain', 'exclusions', 'stop_rule', 'uncertainty', 'sample_size_rationale'):
                if not str(design.get(key, '')).strip():
                    errors.append(f'{pid}: ready experiment design missing {key}')
            n = design.get('independent_units')
            if isinstance(n, bool) or not isinstance(n, int) or n < 2:
                errors.append(f'{pid}: independent_units must be at least two; repeated reads are not independent samples')
        else:
            errors.append(f'{pid}: experiment status must be planned or ready')
    if review['policy'] == 'complete' and seen_designs != protocols.keys():
        pending.append('complete review needs every protocol experiment design')
    if require_ready:
        errors.extend(pending)
    return {'status': 'FAIL' if errors else 'PENDING' if pending else 'REVIEW_RECORDED',
            'errors': errors, 'pending': pending, 'claims_checked': len(seen),
            'scope': 'Recorded review coverage and consistency only; source meaning and reviewer independence are not certified.'}


def audit_review(record, require_ready=False):
    try:
        return _audit_review(record, require_ready)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {'status': 'FAIL', 'errors': ['malformed quality review: ' + str(exc)], 'pending': []}


def selection_errors(record, manifest=None):
    """A priority hypothesis is distinct from a proven winner. Empty primary allowed only in drafts."""
    manifest = manifest or {}
    selection = record.get('assessments', {}).get('selection')
    if selection is None or selection.get('status') == 'not_assessed':
        return []
    errors = []
    status = selection.get('status')
    routes = {r['id']: r for r in record.get('routes', [])}
    compared = selection.get('compared_route_ids', [])
    if status not in {'selected', 'priority_for_validation', 'no_robust_winner'}:
        errors.append('invalid selection status')
    if not selection.get('rationale') or not selection.get('next_decisive_test'):
        errors.append('selection needs rationale and next decisive test')
    if not isinstance(compared, list) or len(set(compared)) < 2 or not set(compared) <= routes.keys():
        errors.append('selection needs at least two distinct existing compared routes')
    if status == 'no_robust_winner':
        if manifest.get('status') == 'complete' or record.get('workflow', {}).get('completed_stage') == 'G5':
            errors.append('no_robust_winner is a draft outcome; complete delivery still requires a priority route')
        if manifest.get('primary_routes') or any(r.get('role') == 'primary' for r in routes.values()):
            errors.append('no_robust_winner cannot declare a primary route')
    elif manifest and not manifest.get('primary_routes'):
        errors.append('selected or priority_for_validation requires primary_routes')
    return errors


def allow_empty_primary(record, manifest):
    try:
        selection = record.get('assessments', {}).get('selection', {})
        return (isinstance(selection, dict) and selection.get('status') == 'no_robust_winner' and not selection_errors(record, manifest))
    except (ValueError, TypeError, KeyError, AttributeError):
        return False


def report_sections(source, record):
    sections = []
    entry = source.get('reader_entry')
    if entry is not None:
        profiles = {'engineering_review': '工程审查入口', 'award_defense': '评奖答辩入口'}
        if not isinstance(entry, dict) or entry.get('profile') not in profiles:
            raise ValueError('reader_entry.profile must be engineering_review or award_defense')
        refs = entry.get('claim_refs', [])
        known = {'/claims/' + c['id'] for c in record.get('claims', [])}
        if not isinstance(refs, list) or not 1 <= len(refs) <= 5 or len(set(refs)) != len(refs) or not set(refs) <= known:
            raise ValueError('reader entry requires one to five unique existing claim_refs')
        blocks = [{'type': 'paragraph', 'claim_ref': ref} for ref in refs]
        for fid in entry.get('figure_ids', []):
            blocks.append({'type': 'figure', 'figure_ref': fid})
        sections.append({'title': profiles[entry['profile']], 'blocks': blocks})
    review = record.get('quality_review', {})
    if source.get('quality_review_surface') and review.get('policy', 'off') != 'off':
        blocks = []
        visible_claims = {b.get('claim_ref') for s in source.get('sections', []) for b in s.get('blocks', [])}
        if isinstance(entry, dict):visible_claims.update(entry.get('claim_refs', []))
        for check in review.get('claim_checks', []):
            cid = check['claim_id']
            # Use bound paragraphs per claim instead of a wide eight-column table.
            for field, label in [('claim_id', '命题'), ('status', '支持判断'), ('support_scope', '支持范围'),
                                 ('unsupported_scope', '不支持范围'), ('action', '处置'), ('rationale', '理由'),
                                 ('reviewer', '复核者'), ('review_mode', '复核方式')]:
                value = check.get(field)
                if value:
                    blocks.append({'type': 'paragraph', 'text_template': label + '：{{/quality_review/claim_checks/' + cid + '/' + field + '}}'})
            if '/claims/' + cid not in visible_claims:
                blocks.append({'type': 'paragraph', 'claim_ref': '/claims/' + cid})
        if blocks:
            sections.append({'title': '证据附件：主张支持审查', 'page_break_before': True, 'blocks': blocks})
        for title, key, fields in [
            ('参数映射卡', 'mapping_cards', [('矛盾', 'contradiction_id'), ('核查', 'review_status'), ('选择理由', 'selection_rationale'), ('判别观察', 'discriminating_observation')]),
            ('试验设计', 'experiment_designs', [('协议', 'protocol_id'), ('状态', 'status'), ('独立样本', 'sample_unit'), ('测量链', 'measurement_chain'), ('不确定性', 'uncertainty')])]:
            if review.get(key):
                sections.append({'title': '证据附件：' + title, 'blocks': [
                    {'type': 'table', 'table_ref': '/quality_review/' + key,
                     'columns': [{'header': label, 'field': field, 'empty_text': '未填写', 'missing_text': '未记录'} for label, field in fields]}]})
    return sections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--draft', type=Path)
    parser.add_argument('--claims', nargs='+', default=[])
    parser.add_argument('--require-ready', action='store_true')
    args = parser.parse_args()
    try:
        record = json.loads(args.record.read_text(encoding='utf-8'))
        if args.draft:
            if args.draft.exists() or args.draft.resolve() == args.record.resolve():
                raise ValueError('draft output must be a new file')
            result = draft_review(record, args.claims)
            args.draft.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            result = audit_review(record, args.require_ready)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get('errors') else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({'status': 'FAIL', 'errors': [str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
