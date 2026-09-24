#!/usr/bin/env python3
"""Portable behavioral regressions: records, generated geometry and actual DOCX.

Run with Python's standard library; no network, browser or field data required.
Synthetic fixtures test consistency only, never engineering validity.
"""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET
import zipfile

sys.dont_write_bytecode = True
from research_contract import audit_record, change_impact, digest
from build_figures import build_figures, expression, render_figure
from build_report import build_report
from report_bindings import verify_docx_bindings, W
from run_tutorial import run
from validate_research import migrate
import validate_deliverables as delivery

ROOT = Path(__file__).resolve().parent.parent


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='triz-pipeline-')
        cls.base = Path(cls.temp.name)
        cls.tutorial = cls.base / 'tutorial'
        run(cls.tutorial)
        # Reuse the established delivery fixture, without duplicating its schema.
        original = delivery.validate
        cls.captured = {}
        def capture(root, manifest, strict=False):
            if not cls.captured:
                shutil.copytree(root, cls.base / 'delivery')
                cls.captured = copy.deepcopy(manifest)
            return original(root, manifest, strict)
        delivery.validate = capture
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                delivery._self_test_v12()
        finally:
            delivery.validate = original

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.root = self.base / self._testMethodName
        shutil.copytree(self.tutorial, self.root)
        self.record = json.loads((self.root / 'research-record.json').read_text(encoding='utf-8'))

    def audit(self):
        return audit_record(self.record, root=self.root)

    def complete_core_case(self):
        record = copy.deepcopy(self.record)
        manifest = {
            'status': 'complete',
            'delivery_level': 'standard',
            'maturity': 'V0',
            'primary_routes': ['R1'],
            'shortlisted_routes': ['R0', 'R1', 'R2'],
        }
        record['workflow'].update(current_stage='G5', completed_stage='G5')
        record['decisions'] = [{
            'id': 'DEC-DIR', 'kind': 'direction_confirmation', 'status': 'confirmed',
            'user_text': '继续按当前方向完成教学回归。', 'scope': '教学回归中的全部候选路线'
        }]
        source = {
            'id': 'SRC-T', 'title': 'Synthetic source', 'creator': 'fixture',
            'date_or_version': '2026', 'stable_identifier': 'FIXTURE-001',
            'url': 'https://example.com/fixture', 'locator': 'section 1',
            'supporting_excerpt_or_fact': 'Synthetic fixture only',
            'target_kind': 'source_component', 'authority': 'low',
            'directness': 'direct', 'independence': 'fixture',
            'currency': 'current', 'scope_match': 'fixture',
            'critical': False, 'limitations': 'Not engineering evidence'
        }
        record['sources'] = [source]
        tracks = [
            'standard_regulation', 'object_structure_material', 'mature_products_process',
            'patent', 'mechanism_literature', 'cross_industry_analogy',
            'opposition_supersystem'
        ]
        record['queries'] = []
        record['research_tracks'] = []
        for index, track in enumerate(tracks, 1):
            qid = f'Q-{index:02d}'
            record['queries'].append({
                'id': qid, 'track': track, 'date': '2026-09-06',
                'entry': 'synthetic fixture', 'query': f'{track} synthetic query',
                'filters': 'none', 'attempt_count': 1, 'status': 'completed',
                'included_source_ids': ['SRC-T'], 'excluded': []
            })
            record['research_tracks'].append({
                'id': f'TRK-{index:02d}', 'track': track, 'status': 'completed',
                'query_ids': [qid], 'source_ids': ['SRC-T'],
                'rationale': 'Synthetic coverage record for contract regression.'
            })
        r0, r1 = record['routes']
        r0['portfolio_roles'] = ['baseline']
        r1['portfolio_roles'] = ['backup']
        r1['improvement_outlook'] = {
            'status': 'identified',
            'items': ['降低调节步骤中的误操作机会'],
            'rationale': 'Synthetic improvement item',
            'validation_needed': 'Compare process error rate'
        }
        r2 = copy.deepcopy(r1)
        r2['id'] = 'R2'
        r2['role'] = 'alternative'
        r2['portfolio_roles'] = ['exploratory']
        r2['improvement_outlook'] = {
            'status': 'unknown', 'items': [],
            'rationale': '进一步提升方向尚需试验后判断',
            'validation_needed': '先完成代表性短样否证'
        }
        for component in r2.get('components', []):
            component['id'] = 'R2-' + str(component['id'])
        for effect in r2.get('active_effects', []):
            effect['source'] = 'R2-' + str(effect.get('source', 'SRC'))
        record['routes'].append(r2)
        record['assessments']['route_portfolio'] = {
            'supersystem_applicable': False,
            'supersystem_rationale': '本教学回归不模拟可适用的超系统替代。'
        }
        record['assessments']['robustness_review'] = {
            'status': 'reviewed',
            'strongest_objection': '当前候选的保持作用可能在真实载荷下失效。',
            'objection_evidence_status': 'H',
            'opposing_source_ids': [],
            'exit_condition': '若代表性短样在冻结载荷下超过滑移判据则退出该路线。',
            'strongest_support_claim_id': 'CLM-001',
            'without_strongest_support': 'unknown',
            'rationale': '移除当前主机理假设后，路线尚无足够证据维持推荐。'
        }
        protocols = [
            {
                'id': 'P-R1', 'route_ids': ['R1'], 'scope': 'short_sample',
                'sampling_plan': 'Synthetic protocol for R1',
                'metrics': [{'id': 'M1', 'unit': '1', 'criterion': {'operator': '<=', 'value': 1}}],
                'stop_rule': 'Stop on criterion failure'
            },
            {
                'id': 'P-R2', 'route_ids': ['R2'], 'scope': 'short_sample',
                'sampling_plan': 'Synthetic protocol for R2',
                'metrics': [{'id': 'M2', 'unit': '1', 'criterion': {'operator': '<=', 'value': 1}}],
                'stop_rule': 'Stop on criterion failure'
            }
        ]
        record['models_and_tests']['protocols'] = protocols
        record['hazards'] = [
            {
                'id': 'HZ-R1', 'route_ids': ['R1'],
                'event': '夹紧不足导致滑移', 'causes': ['预紧力不足'],
                'consequences': ['定位失效'], 'controls': ['限位与预紧检查'],
                'residual_risk': '仍需短样确认保持能力',
                'protocol_id': 'P-R1', 'stop_condition': '滑移超过冻结判据即停止',
                'evidence_ids': ['IN-01']
            },
            {
                'id': 'HZ-R2', 'route_ids': ['R2'],
                'event': '探索结构作用不稳定', 'causes': ['参数窗口未知'],
                'consequences': ['无法保持目标状态'], 'controls': ['先做低能量短样'],
                'residual_risk': '机理未验证',
                'protocol_id': 'P-R2', 'stop_condition': '任一硬门槛失败即停止',
                'evidence_ids': ['IN-01']
            }
        ]
        record['models_and_tests']['benefit_assessment'] = {
            'economic': {
                'status': 'pending-data',
                'formula': 'ΔH=(H0-H1)×Q',
                'inputs_needed': ['H0', 'H1', 'Q'],
                'scenario_plan': '分别计算保守、基准和理想三种情景。',
                'rationale': '尚无真实节拍和成本数据。'
            },
            'social': {
                'status': 'pending-data',
                'metrics': [{
                    'id': 'SB-01', 'name': '误操作次数', 'unit': '次/任务',
                    'target_direction': 'decrease', 'measurement': '逐任务记录异常操作',
                    'evidence_status': 'H', 'validation_needed': '完整流程对照记录'
                }],
                'rationale': '指标已定义，等待流程试验。'
            }
        }
        record['implementation_plan'] = {
            'status': 'ready',
            'next_decisive_test': '执行冻结载荷下的代表性短样滑移试验。',
            'stage_gates': [{
                'stage': 'V1', 'entry_condition': '对象与载荷冻结',
                'pass_condition': '全部短样满足滑移判据',
                'exit_condition': '任一安全或质量硬门槛失败'
            }],
            'procurement_or_exit_conditions': ['成熟采购方案满足接口时优先比较', '短样失败则退出自研路线'],
            'current_boundary': '仅限教学回归和 V0 概念，不代表现场可用。',
            'open_unknowns': ['真实载荷和目标对象适配仍未知'],
            'report_summary': '先做最低成本机理否证，再决定进入完整流程或转向成熟替代。'
        }
        return record, manifest

    def delivery_case(self, mutate=None, text=None):
        root = self.root / 'delivery'
        shutil.copytree(self.base / 'delivery', root)
        manifest = copy.deepcopy(self.captured)
        record = json.loads((root / 'research-record.json').read_text(encoding='utf-8'))
        if mutate:
            mutate(manifest, record)
        write_json(root / 'research-record.json', record)
        if text:
            (root / '02-report.md').write_text(text, encoding='utf-8')
        return delivery.validate(root, manifest, strict=True)

    def rewrite_docx(self, transform):
        target = self.root / 'tutorial-report.docx'
        with zipfile.ZipFile(target) as package:
            parts = {n: package.read(n) for n in package.namelist()}
        transform(parts)
        with zipfile.ZipFile(target, 'w') as package:
            for name, value in parts.items():
                package.writestr(name, value)

    def verify(self):
        return verify_docx_bindings(self.root / 'tutorial-report.docx', self.root / 'report-source.json')

    def add_measurement(self, value=0.2):
        raw = self.root / 'raw.csv'
        raw.write_text('sample,slip_mm\n1,' + str(value) + '\n', encoding='utf-8')
        self.record['models_and_tests']['protocols'] = [{
            'id': 'PTEST-01', 'route_ids': ['R1'], 'scope': 'short_sample',
            'sampling_plan': 'Synthetic single observation for software regression',
            'metrics': [{'id': 'SLIP', 'unit': 'mm', 'criterion': {'operator': '<=', 'value': 0.5}}],
            'stop_rule': 'Stop at slip above criterion'}]
        test = {'id': 'TEST-01', 'route_id': 'R1', 'protocol_id': 'PTEST-01',
                'target_kind': 'proposed_system', 'status': 'completed', 'maturity': 'V1',
                'date': '2026-09-06', 'conditions': 'Synthetic fixture, no physical trial',
                'sample_count': 1, 'claim_ids': ['CLM-001'],
                'results': [{'metric_id': 'SLIP', 'value': value, 'unit': 'mm'}],
                'raw_artifacts': [{'path': raw.name, 'sha256': digest(raw)}]}
        self.record['models_and_tests']['tests'] = [test]
        claim = self.record['claims'][0]
        claim.update(evidence_status='M', test_ids=['TEST-01'])
        return test

    def test_working_record_and_generated_report(self):
        self.assertEqual(self.audit()['errors'], [])
        result = self.verify()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['bound_blocks'], 7)
        self.assertGreater(result['unbound_narrative_blocks'], 0)

    def test_complete_core_contract_passes(self):
        record, manifest = self.complete_core_case()
        self.assertEqual(audit_record(record, manifest, root=self.root)['errors'], [])

    def test_complete_requires_all_deep_research_tracks(self):
        record, manifest = self.complete_core_case()
        record['research_tracks'].pop()
        errors = audit_record(record, manifest, root=self.root)['errors']
        self.assertTrue(any('seven-track coverage' in e for e in errors), errors)

    def test_complete_requires_distinct_portfolio_roles(self):
        record, manifest = self.complete_core_case()
        record['routes'][2]['portfolio_roles'] = ['backup']
        errors = audit_record(record, manifest, root=self.root)['errors']
        self.assertTrue(any('exploratory' in e or 'distinct routes' in e for e in errors), errors)

    def test_complete_requires_fmea_per_active_route(self):
        record, manifest = self.complete_core_case()
        record['hazards'] = [record['hazards'][0]]
        errors = audit_record(record, manifest, root=self.root)['errors']
        self.assertTrue(any('FMEA/hazard' in e and 'R2' in e for e in errors), errors)

    def test_complete_requires_further_improvement_outlook(self):
        record, manifest = self.complete_core_case()
        record['routes'][1].pop('improvement_outlook')
        errors = audit_record(record, manifest, root=self.root)['errors']
        self.assertTrue(any('improvement_outlook' in e for e in errors), errors)

    def test_complete_requires_social_benefit_metric(self):
        record, manifest = self.complete_core_case()
        record['models_and_tests']['benefit_assessment']['social']['metrics'] = []
        errors = audit_record(record, manifest, root=self.root)['errors']
        self.assertTrue(any('social benefit' in e for e in errors), errors)

    def test_complete_requires_strong_counterevidence_review(self):
        record, manifest = self.complete_core_case()
        record['assessments']['robustness_review']['status'] = 'pending'
        errors = audit_record(record, manifest, root=self.root)['errors']
        self.assertTrue(any('robustness_review' in e for e in errors), errors)

    def test_complete_requires_implementation_plan(self):
        record, manifest = self.complete_core_case()
        record['implementation_plan']['status'] = 'pending'
        errors = audit_record(record, manifest, root=self.root)['errors']
        self.assertTrue(any('implementation_plan.status=ready' in e for e in errors), errors)

    def test_hard_gate_blocks_selected_route(self):
        self.record['assessments']['gates'] = [{'id': 'HARD-1', 'target_id': 'R1', 'status': 'fail'}]
        result = self.audit()
        self.assertEqual(result['route_eligibility']['R1']['status'], 'blocked')
        self.assertTrue(result['errors'])

    def test_conflicting_effects_block_selected_route(self):
        route = self.record['routes'][1]
        first = route['active_effects'][0]['id']
        route['active_effects'].append({'id': 'ACT-2', 'type': 'thermal'})
        route['interactions'] = [{'effect_ids': [first, 'ACT-2'], 'status': 'conflict'}]
        self.assertEqual(self.audit()['route_eligibility']['R1']['status'], 'blocked')

    def test_pairwise_coverage_and_passive_read(self):
        route = self.record['routes'][1]
        first = route['active_effects'][0]['id']
        route['active_effects'] += [{'id': 'ACT-2', 'type': 'thermal'}, {'id': 'ACT-3', 'type': 'electrical'}]
        route['interactions'] = [{'effect_ids': [first, 'ACT-2'], 'status': 'compatible'},
                                 {'effect_ids': ['ACT-2', 'ACT-3'], 'status': 'compatible'}]
        self.assertTrue(self.audit()['errors'])
        route['interactions'].append({'effect_ids': [first, 'ACT-3'], 'status': 'compatible'})
        route['active_effects'].append({'id': 'READ-1', 'type': 'passive'})
        route['interactions'].append({'effect_ids': [first, 'READ-1'], 'status': 'compatible'})
        self.assertEqual(self.audit()['errors'], [])

    def test_unearned_maturity_is_rejected(self):
        self.record['routes'][1]['maturity'] = 'V3'
        self.record['claims'][0]['evidence_status'] = 'M'
        result = self.audit()
        self.assertEqual(result['maturity_support']['R1'], 'V0')
        self.assertTrue(result['errors'])

    def test_measurement_requires_raw_hash_and_metric_units(self):
        test = self.add_measurement()
        self.assertEqual(self.audit()['maturity_support']['R1'], 'V1')
        self.assertEqual(self.audit()['errors'], [])
        test['results'][0]['unit'] = 's'
        self.assertTrue(self.audit()['errors'])
        test['results'][0]['unit'] = 'mm'
        (self.root / 'raw.csv').write_text('changed', encoding='utf-8')
        self.assertTrue(self.audit()['errors'])

    def test_negative_measurement_is_evidence_without_maturity(self):
        self.add_measurement(2.0)
        result = self.audit()
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['maturity_support']['R1'], 'V0')
        self.assertTrue(result['warnings'])

    def test_planned_baseline_cannot_support_v2(self):
        test = self.add_measurement()
        test.update(maturity='V2', baseline_test_id='BASE-01')
        self.record['models_and_tests']['protocols'][0]['scope'] = 'full_process'
        self.record['models_and_tests']['tests'].append({'id': 'BASE-01', 'status': 'planned'})
        self.assertTrue(self.audit()['errors'])
        self.assertEqual(self.audit()['maturity_support']['R1'], 'V0')

    def test_incomparable_valid_baseline_cannot_support_v2(self):
        test=self.add_measurement()
        test.update(maturity='V2',baseline_test_id='BASE-01',comparison_conditions={'temperature_C':20},comparison_rationale='Same sample lot, complete procedure')
        protocol=self.record['models_and_tests']['protocols'][0]
        protocol.update(scope='full_process',comparison_basis={'object_population':'lot A','metric_definition':'SLIP','reference_points':'jaw edge','instrument_chain':'CAL-1'})
        bp=copy.deepcopy(protocol);bp.update(id='PB',route_ids=['R0'])
        base=copy.deepcopy(test);base.update(id='BASE-01',route_id='R0',protocol_id='PB',target_kind='baseline_system',maturity='V1',claim_ids=[])
        base.pop('baseline_test_id');self.record['models_and_tests']['protocols'].append(bp);self.record['models_and_tests']['tests'].append(base)
        self.assertEqual(self.audit()['maturity_support']['R1'],'V2')
        bp['comparison_basis']['instrument_chain']='UNRELATED'
        result=self.audit()
        self.assertEqual(result['maturity_support']['R1'],'V0')
        self.assertTrue(any('incomparable' in e for e in result['errors']))

    def test_invalid_query_and_legitimate_dimensions(self):
        def invalid(m, r):
            r['queries'][0]['date'] = '2026-02-30'
            r['queries'][0].pop('filters')
            r['queries'][0].pop('excluded')
        self.assertEqual(self.delivery_case(invalid)['status'], 'FAIL')

    def test_query_dimensions_are_one_search(self):
        def dimensions(m, r):
            r['queries'][0]['query'] = '4×4 mm2 电缆 原厂规格'
        self.assertEqual(self.delivery_case(dimensions)['status'], 'PASS')

    def test_unknown_formula_is_unchecked(self):
        self.record['models_and_tests']['benefit_scenarios'] = [{'id': 'BEN-1', 'formula_type': 'custom', 'expected_result': 999}]
        self.assertEqual(self.audit()['computational_consistency'], 'NOT_CHECKED')
        self.record['workflow']['completed_stage'] = 'G5'
        self.assertTrue(self.audit()['errors'])

    def test_negative_weight_and_nonfinite_parameters(self):
        self.record['assessments']['scorecard'] = {'used': True, 'dimensions': [{'weight': -2}]}
        self.assertTrue(self.audit()['errors'])
        self.record['assessments']['scorecard']['used'] = False
        self.record['parameters'][0]['value'] = float('nan')
        self.assertTrue(self.audit()['errors'])

    def test_actual_public_benefit_differs(self):
        model = {'id': 'BEN-01', 'formula_type': 'linear_difference_rate',
                 'inputs': {'baseline': 10, 'candidate': 5, 'quantity': 2, 'unit_rate': 3},
                 'expected_result': 30, 'unit': '元', 'outputs': [{'artifact': 'report', 'value': 30, 'unit': '元'}]}
        self.record['models_and_tests']['benefit_scenarios'] = [model]
        result = audit_record(self.record, root=self.root, public_documents={'main-report': 'BEN-01：3000 元'})
        self.assertTrue(any('actual public value' in e for e in result['errors']))

    def test_missing_queries_distinguishes_work_from_completion(self):
        self.assertEqual(self.audit()['errors'], [])
        self.record['workflow']['completed_stage'] = 'G2'
        self.assertTrue(any('executed query' in e for e in self.audit()['errors']))

    def test_unresolved_intake_reference(self):
        self.record['problems'][0]['input_ids'] = ['NOT-PRESENT']
        self.assertTrue(self.audit()['errors'])

    def test_actual_docx_text_tamper(self):
        def mutate(parts):
            document = ET.fromstring(parts['word/document.xml'])
            document.find('.//' + W + 'sdtContent//' + W + 't').text = 'tampered 3000'
            parts['word/document.xml'] = ET.tostring(document, encoding='utf-8')
        self.rewrite_docx(mutate)
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_actual_unbound_prose_tamper(self):
        def mutate(parts):
            document=ET.fromstring(parts['word/document.xml'])
            paragraph=document.find(W+'body/'+W+'p')
            paragraph.find('.//'+W+'t').text='Unbound claim: efficiency 35%'
            parts['word/document.xml']=ET.tostring(document,encoding='utf-8')
        self.rewrite_docx(mutate)
        self.assertTrue(any('narrative differs' in e for e in self.verify()['errors']))

    def test_actual_embedded_figure_shrink(self):
        def mutate(parts):
            document=ET.fromstring(parts['word/document.xml'])
            wp='{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
            for extent in document.iter(wp+'extent'):
                extent.set('cx',str(int(extent.get('cx'))//10));extent.set('cy',str(int(extent.get('cy'))//10))
            parts['word/document.xml']=ET.tostring(document,encoding='utf-8')
        self.rewrite_docx(mutate)
        self.assertTrue(any('actual DOCX effective' in e for e in self.verify()['errors']))

    def test_critical_free_text_cannot_complete(self):
        path=self.root/'report-source.json';source=json.loads(path.read_text(encoding='utf-8'))
        source['critical_facts_policy']='bound'
        source['sections'][0]['blocks'].append({'type':'paragraph','text':'预计提高效率 35%。'})
        write_json(path,source)
        with self.assertRaisesRegex(ValueError,'critical fact'):build_report(path,self.root/'invalid.docx')

    def test_run_splitting_does_not_change_bound_text(self):
        def mutate(parts):
            document = ET.fromstring(parts['word/document.xml'])
            paragraph = document.find('.//' + W + 'sdtContent/' + W + 'p')
            node = paragraph.find('.//' + W + 't');value = node.text
            node.text = value[:5]
            ET.SubElement(ET.SubElement(paragraph, W + 'r'), W + 't').text = value[5:]
            parts['word/document.xml'] = ET.tostring(document, encoding='utf-8')
        self.rewrite_docx(mutate)
        self.assertEqual(self.verify()['status'], 'PASS')

    def test_actual_docx_image_tamper(self):
        def mutate(parts):
            name = next(n for n in parts if n.startswith('word/media/'))
            parts[name] += b'changed'
        self.rewrite_docx(mutate)
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_parameter_change_requires_regeneration(self):
        old = copy.deepcopy(self.record)
        next(p for p in self.record['parameters'] if p['id'] == 'P-X')['value'] = 95
        write_json(self.root / 'research-record.json', self.record)
        with self.assertRaises(ValueError):
            self.verify()
        source_path = self.root / 'report-source.json'
        source = json.loads(source_path.read_text(encoding='utf-8'))
        source['research_record_sha256'] = digest(self.root / 'research-record.json')
        write_json(source_path, source)
        with self.assertRaises(ValueError):
            build_report(source_path, self.root / 'stale.docx')
        original_svg = (self.root / 'figures/FIG-DESIGN.svg').read_text(encoding='utf-8')
        build_figures(self.root / 'research-record.json', self.root / 'figures')
        self.assertNotEqual(original_svg, (self.root / 'figures/FIG-DESIGN.svg').read_text(encoding='utf-8'))
        build_report(source_path, self.root / 'tutorial-report.docx')
        self.assertEqual(self.verify()['status'], 'PASS')
        self.assertIn('FIG-DESIGN', change_impact(old, self.record)['review_required_ids'])

    def test_geometry_expression_and_frame_id_restrictions(self):
        for expr in ['__import__("os")', 'L ** 100', 'L / 0', 'unknown + 1']:
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                expression({'expr': expr}, {'L': 20})
        spec = copy.deepcopy(self.record['figure_specs'][1])
        spec['frames'][0]['id'] = 'bad" onload="run()'
        with self.assertRaises(ValueError):
            render_figure(spec, self.record)

    def test_legacy_migration_preserves_facts(self):
        old = {'schema_version': '1.0', 'project': {'title': 'Legacy', 'maturity': 'V0'}, 'claims': [{'id': 'C1', 'text': 'uncertain'}]}
        new = migrate(old)
        self.assertEqual(new['claims'], old['claims'])
        self.assertEqual(old['schema_version'], '1.0')
        self.assertEqual(new['inputs'], [])
        self.assertIsNone(new['workflow']['completed_stage'])

    def test_figure_order_reads_actual_docx(self):
        manifest = {'artifacts': [{'role': 'main-report', 'path': 'tutorial-report.docx'}],
                    'report_figure_order': {'body_start_marker': '方案总览', 'ordered_numbers': ['1','2','3'], 'summary_preview_numbers': []}}
        errors = []
        delivery._check_actual_figure_order(self.root, manifest, errors)
        self.assertEqual(errors, [])
        manifest['report_figure_order']['ordered_numbers'] = ['3','2','1']
        delivery._check_actual_figure_order(self.root, manifest, errors)
        self.assertTrue(errors)

    def test_generated_svg_meets_delivery_contract(self):
        for spec in self.record['figure_specs']:
            item = dict(spec, display_width_pt=450, frame_count=len(spec.get('frames',[])))
            errors, warnings = [], []
            delivery._check_svg(self.root / 'figures' / (spec['id']+'.svg'), item, errors, warnings)
            self.assertEqual(errors, [])
            # Rectangular geometry needs reader review; marker paths no longer
            # suppress this advisory. It is not an engineering validity test.
            self.assertTrue(all('box-only' in warning for warning in warnings))
        errors=[]
        delivery._check_figure_numbering([{'number': str(i)} for i in [1,2,3]], errors)
        self.assertEqual(errors, [])

    def test_malformed_record_returns_failure(self):
        self.record['parameters'] = [False]
        self.assertTrue(self.audit()['errors'])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(PipelineTests))
    if result.wasSuccessful():
        print('PIPELINE_SELF_TEST_PASS', result.testsRun)
    raise SystemExit(0 if result.wasSuccessful() else 2)
