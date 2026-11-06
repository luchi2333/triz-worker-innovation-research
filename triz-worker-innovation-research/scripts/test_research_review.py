"""Focused positive/negative review, compatibility, binding and recommendation regressions."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
from research_review import (allow_empty_primary, audit_review, claim_basis, draft_review,
                             fingerprint, mapping_cards, selection_errors)
from research_contract import audit_record, digest
from validate_research import migrate
from build_report import build_report
from report_bindings import compile_source, verify_docx_bindings


def fixture():
    return {'schema_version': '1.1', 'workflow': {'current_stage': 'G0'},
            'claims': [{'id': 'C1', 'text': '来源描述子组件限矩', 'evidence_status': 'S',
                        'supporting_source_ids': ['S1'], 'conditions': '仅指来源组件',
                        'test_ids': []}],
            'sources': [{'id': 'S1', 'locator': 'section 2', 'scope': 'component'}],
            'routes': [{'id': 'R1', 'role': 'exploratory'}, {'id': 'R2', 'role': 'backup'}],
            'models_and_tests': {'tests': [], 'protocols': []}}


def reviewed(record):
    record['quality_review'] = draft_review(record, ['C1'])
    record['quality_review']['claim_checks'][0].update(
        status='supported', source_ids=['S1'], support_scope='来源 section 2 仅支持该组件的限矩机构',
        rationale='对照完整来源边界，不外推整机能力', action='retain', reviewer='fixture serial reviewer',
        reviewed_at='2026-11-06', review_mode='serial')
    return record


class ReviewTests(unittest.TestCase):
    def test_legacy_not_checked_and_idempotent_migration(self):
        record = fixture()
        self.assertEqual(audit_review(record)['status'], 'NOT_CHECKED')
        migrated = migrate(record)
        self.assertEqual(migrate(migrated), migrated)
        self.assertEqual(migrated['claims'], record['claims'])
        self.assertEqual(audit_review(migrated)['status'], 'NOT_CHECKED')

    def test_draft_does_not_invent_decisions_or_evidence(self):
        record = fixture()
        record['quality_review'] = draft_review(record, ['C1'])
        self.assertEqual(audit_review(record)['status'], 'PENDING')
        self.assertEqual(audit_review(record, True)['status'], 'FAIL')
        self.assertEqual(record['quality_review']['claim_checks'][0]['source_ids'], [])

    def test_sourced_component_positive(self):
        self.assertEqual(audit_review(reviewed(fixture()), True)['status'], 'REVIEW_RECORDED')

    def test_hypothesis_example_positive(self):
        record = fixture()
        record['claims'][0].update(evidence_status='H', allowed_wording='H 算例仅在假定载荷下成立',
                                   next_validation='采集配对载荷及压痕', conditions='假定载荷，不外推现场')
        reviewed(record)['quality_review']['claim_checks'][0].update(status='hypothesis', source_ids=[])
        self.assertFalse(audit_review(record, True)['errors'])

    def test_h_cannot_be_verified_performance(self):
        record = fixture()
        record['claims'][0]['evidence_status'] = 'H'
        self.assertTrue(audit_review(reviewed(record), True)['errors'])

    def test_unsupported_cannot_retain_or_finish_qualification(self):
        for status in ('partial', 'unsupported', 'unverifiable'):
            record = reviewed(fixture())
            check = record['quality_review']['claim_checks'][0]
            check.update(status=status, unsupported_scope='没有整机试验')
            self.assertTrue(audit_review(record, True)['errors'])
            check['action'] = 'qualify'
            self.assertEqual(audit_review(record)['status'], 'PENDING')
            self.assertTrue(audit_review(record, True)['errors'])

    def test_missing_source_or_unattached_reference_rejected(self):
        for ids in ([], ['missing']):
            record = reviewed(fixture())
            record['quality_review']['claim_checks'][0]['source_ids'] = ids
            self.assertTrue(audit_review(record, True)['errors'])

    def test_pending_measurement_cannot_support_m(self):
        record = fixture()
        record['claims'][0].update(evidence_status='M', test_ids=['T1'])
        record['models_and_tests']['tests'] = [{'id': 'T1', 'status': 'planned'}]
        reviewed(record)['quality_review']['claim_checks'][0]['test_ids'] = ['T1']
        self.assertTrue(audit_review(record, True)['errors'])

    def test_completed_test_reference_retained_without_certifying_raw_data(self):
        record = fixture()
        record['claims'][0].update(evidence_status='M', test_ids=['T1'])
        record['models_and_tests']['tests'] = [{'id': 'T1', 'status': 'completed'}]
        reviewed(record)['quality_review']['claim_checks'][0]['test_ids'] = ['T1']
        self.assertEqual(audit_review(record, True)['status'], 'REVIEW_RECORDED')
        self.assertTrue(audit_record(record)['errors'])  # Raw-data and core M contract still enforced.

    def test_claim_source_and_test_edits_invalidate_review(self):
        for mutate in (lambda r: r['claims'][0].update(text='已验证整机安全'),
                       lambda r: r['sources'][0].update(scope='different source content')):
            record = reviewed(fixture())
            mutate(record)
            self.assertIn('stale', ' '.join(audit_review(record)['errors']))

    def test_complete_scope_cannot_omit_claim(self):
        record = reviewed(fixture())
        record['quality_review']['policy'] = 'complete'
        record['claims'].append({'id': 'C2'})
        self.assertTrue(audit_review(record, True)['errors'])

    def test_mapping_preserves_no_contradiction_and_never_looks_up_cell(self):
        record = fixture()
        record['contradictions'] = [{'id': 'CON1', 'useful_result': '无匹配词',
                                    'worsened_result': '无匹配词', 'eligibility': 'no_triz_contradiction'}]
        cards = mapping_cards(record)
        self.assertEqual(cards[0]['eligibility'], 'no_triz_contradiction')
        self.assertEqual(cards[0]['candidates'], {'improving': [], 'worsening': []})
        self.assertNotIn('principles', cards[0])
        reviewed(record)['quality_review']['mapping_cards'] = cards
        self.assertEqual(audit_review(record)['status'], 'PENDING')
        cards[0].update(review_status='reviewed', selection_rationale='不需要强行映射', discriminating_observation='先判断是否存在恶化结果')
        self.assertFalse(audit_review(record, True)['errors'])
        record['contradictions'][0]['eligibility'] = 'assumption_only'
        self.assertTrue(audit_review(record, True)['errors'])

    def test_mapping_card_cannot_rewrite_fact_or_parameter_vocabulary(self):
        record = fixture()
        record['contradictions'] = [{'id': 'CON1', 'useful_result': '压紧后位置稳定', 'worsened_result': '压痕增加'}]
        reviewed(record)
        card = record['quality_review']['mapping_cards'][0]
        card.update(review_status='reviewed', selection_rationale='以位置保持为收益', discriminating_observation='观察是否长期故障问题')
        card['useful_result'] = '伪造收益'
        self.assertTrue(audit_review(record)['errors'])
        card['useful_result'] = record['contradictions'][0]['useful_result']
        card['candidates']['improving'] = [{'id': 44, 'name': '虚构参数'}]
        self.assertTrue(audit_review(record)['errors'])

    def test_enabled_pending_review_reaches_core_gate(self):
        record = fixture()
        record['quality_review'] = draft_review(record, ['C1'])
        result = audit_record(record, {'status':'complete'})
        self.assertEqual(result['quality_review']['status'], 'FAIL')
        self.assertIn('claim support review pending', ' '.join(result['errors']))

    def test_experiment_independent_units_and_plan_status(self):
        record = reviewed(fixture())
        protocol = {'id': 'P1', 'baseline': 'R0'}
        record['models_and_tests']['protocols'] = [protocol]
        design = {'protocol_id': 'P1', 'basis_sha256': fingerprint(protocol), 'status': 'planned'}
        record['quality_review']['experiment_designs'] = [design]
        self.assertEqual(audit_review(record)['status'], 'PENDING')
        compiled = compile_source({'sections':[], 'quality_review_surface':True}, record, Path.cwd())
        self.assertIn('未记录', str(compiled))
        design.update(status='ready', independent_units=2)
        for key in ('sample_unit', 'baseline', 'allocation_order', 'measurement_chain', 'exclusions', 'stop_rule', 'uncertainty', 'sample_size_rationale'):
            design[key] = '明确记录的试验设计项'
        self.assertFalse(audit_review(record, True)['errors'])
        for n in (True, 1, 2.5, '3'):
            design['independent_units'] = n
            self.assertTrue(audit_review(record, True)['errors'])

    def test_malformed_review_fails_closed(self):
        for data in ([], {'policy': 'other'}, {'policy': 'focused', 'claim_checks': [None]}):
            record = fixture(); record['quality_review'] = data
            self.assertEqual(audit_review(record)['status'], 'FAIL')

    def test_no_winner_only_relaxes_draft_primary_requirement(self):
        record = fixture()
        record['assessments'] = {'selection': {'status': 'no_robust_winner', 'compared_route_ids': ['R1', 'R2'],
                                              'rationale': '缺少配对试验无法稳健排名', 'next_decisive_test': '同材样片配对试验'}}
        manifest = {'status': 'degraded', 'primary_routes': []}
        self.assertTrue(allow_empty_primary(record, manifest))
        self.assertFalse(allow_empty_primary(record, dict(manifest, status='complete')))
        self.assertTrue(selection_errors(record, dict(manifest, primary_routes=['R1'])))
        record['assessments']['selection']['compared_route_ids'] = ['R1', 'missing']
        self.assertFalse(allow_empty_primary(record, manifest))

    def test_actual_docx_reader_profiles_and_audit_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = reviewed(fixture())
            (root/'record.json').write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
            for profile in ('engineering_review', 'award_defense'):
                source = {'schema_version': '1.3', 'title': '审查样例', 'critical_facts_policy': 'bound',
                          'research_record_path': 'record.json', 'research_record_sha256': digest(root/'record.json'),
                          'reader_entry': {'profile': profile, 'claim_refs': ['/claims/C1']},
                          'quality_review_surface': True, 'sections': []}
                source_path = root/(profile+'.json'); docx = root/(profile+'.docx')
                source_path.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
                build_report(source_path, docx)
                self.assertEqual(verify_docx_bindings(docx, source_path, True)['status'], 'PASS')
                source['quality_review_surface'] = False
                source_path.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
                self.assertTrue(verify_docx_bindings(docx, source_path, True)['errors'])
            source['reader_entry']['claim_refs'] = ['/claims/missing']
            with self.assertRaises(ValueError):
                compile_source(source, record, root)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ReviewTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print('RESEARCH_REVIEW_SELF_TEST_PASS')
    raise SystemExit(0 if result.wasSuccessful() else 2)
