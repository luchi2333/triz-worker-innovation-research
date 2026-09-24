"""Behavioral tests using actual generated DOCX/SVG, with synthetic review receipts.

These fixtures test contracts, not a real engineering review or performance.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
from build_report import build_report
from report_quality import audit_quality, docx_style, svg_style, SECTIONS, GLOBAL_SECTIONS
from validate_deliverables import _check_svg
import validate_deliverables as delivery
from report_bindings import canonical_text, verify_docx_bindings


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record = {'schema_version': '1.1', 'routes': [{'id': 'R1', 'role': 'primary'}]}
        self.record['models_and_tests'] = {'protocols': [{'id': 'P1', 'route_ids': ['R1'], 'scope': 'short_sample',
            'sampling_plan': '两组明确 H 数列的逐窗回放，不外推现场性能',
            'metrics': [{'id': 'state_matches', 'unit': 'count', 'criterion': {'operator': '==', 'value': 4}}],
            'stop_rule': '任一窗口状态不符合示例则停止并核对运算'}]}
        self.write('research-record.json', self.record)
        self.paragraphs = {
            'input_output': '输入为每小时无量纲残差 x；输出是关注状态。缺失读数不进入拟合。',
            'mechanism': '对三点求最小二乘斜率 b=sum((t-mean(t))*(x-mean(x)))/sum((t-mean(t))^2)。',
            'implementation': '每小时滚动一窗；b<-0.5/h 时连续计数加一，否则清零；两窗才关注。门槛为 H，需用独立健康集校准。',
            'worked_example': 'H 算例 t=[0,1,2]h，x=[10,9,8]，分子=-2，分母=2，b=-1/h；计数从0变1，还不能关注。',
            'validation': '离线回放两组 H 数列：[10,9,8,7]第二窗进入关注；[10,10,10,10]保持正常。缺失窗计数清零，逐窗保存 b、计数、状态。此为逻辑检验，不代表现场性能。',
            'innovation_attribution': '成熟部分是滚动窗口、最小二乘斜率和连续计数逻辑；本样例仅把这些已有方法组合成候选判定流程，不把通用算法本身声称为创新。候选差异仅限于面向目标场景的状态组合与退出规则，仍需检索和验证。',
            'further_improvement': '后续提升重点是降低跨人员操作波动、提高异常回退清晰度，并保留维护和校准可达性。',
            'challenge_review': '最强反对意见是固定阈值可能对工况漂移敏感；若独立健康集无法稳定分离则退出。去掉当前最强支持示例后，结论仍保持未知而不是继续声称有效。',
        }
        self.report_paragraphs = {
            'problem_scope': '研究对象、目标指标和禁止外推边界已在本报告中明确，未取得的现场参数保持待验证。',
            'triz_analysis': 'TRIZ 分析记录了变量方向、真实矛盾判定、候选原理和不使用矩阵的条件。',
            'deep_research': '深度研究按预定义轨道记录检索、来源、纳入排除和反对证据，未覆盖轨道明确说明原因。',
            'route_comparison': '候选路线包含成熟基准、工程后备和探索路线，比较结论保留退出条件与最强反对意见。',
            'safety_fmea': '安全章节记录危险事件、原因、后果、控制、残余风险、验证协议和立即停止条件。',
            'benefits': '效益章节区分经济模型、缺失输入和社会效益可测指标，不把假设数据写成已实现收益。',
            'implementation_path': '实施路径列出下一项决定性试验、阶段闸门、采购或退出自研条件以及未解决未知。',
        }
        source = {'schema_version': '1.2', 'research_record_path': 'research-record.json',
                  'research_record_sha256': self.sha('research-record.json'), 'title': 'H 算法逻辑样例',
                  'sections': [{'heading': '候选设计', 'blocks': [
                      *[{'type': 'paragraph', 'text': text} for text in self.report_paragraphs.values()],
                      *[{'type': 'paragraph', 'text': text} for text in self.paragraphs.values()],
                      {'type': 'table', 'headers': ['输入', '斜率'], 'rows': [['H: 10,9,8', '-1/h']]}]}]}
        self.write('source.json', source)
        build_report(self.root / 'source.json', self.root / 'report.docx')
        self.svg = '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400" viewBox="0 0 800 400"><title>运算状态</title><desc>滚动斜率及连续计数</desc><defs><marker id="a"><path d="M0,0 L6,3 L0,6" fill="#000"/></marker></defs><rect x="20" y="40" width="750" height="100" fill="#fff" stroke="#000"/><text x="35" y="85" font-size="20">b 计算 → b &lt; -0.5/h → 连续两窗 → 关注</text></svg>'
        (self.root / 'mechanism.svg').write_text(self.svg, encoding='utf-8')
        self.manifest = {'status': 'complete', 'research_record': {'path': 'research-record.json'},
                         'artifacts': [{'role': 'main-report', 'path': 'report.docx'}],
                         'figures': [{'id': 'FIG1', 'source_svg': 'mechanism.svg', 'figure_type': 'F8-process-operation'}]}
        anchors = {key: self.anchor(value) for key, value in self.paragraphs.items()}
        report_anchors = {key: self.anchor(value) for key, value in self.report_paragraphs.items()}
        self.dossier = {'route_id': 'R1', 'domain': 'software', 'protocol_id': 'P1', **anchors,
                        'diagram': {'figure_id': 'FIG1', 'kind': 'algorithm-state',
                                    'why_this_explains_mechanism': '阈值与连续计数对应实现公式；必须结合正文的例算阅读。',
                                    'report_evidence': anchors['implementation']},
                        'reader_review': {'status': 'reviewed', 'reviewer': 'synthetic test fixture; no real reviewer', 'mode': 'serial-reader',
                                          'trace_example': {'answer': 'H -2/2=-1/h，第一次不关注。', 'evidence': anchors['worked_example']},
                                          'distinguish_failure': {'answer': '平坦序列不触发；缺失窗清零。', 'evidence': anchors['validation']},
                                          'reproduce_test': {'answer': '按两组给定数列逐窗保存三个字段。', 'evidence': anchors['validation']}, 'open_issues': []}}
        self.receipt = {'report_sections': report_anchors, 'technical_dossiers': [self.dossier]}

    def sha(self, name):
        return hashlib.sha256((self.root / name).read_bytes()).hexdigest()

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')

    def anchor(self, quote):
        return {'artifact_path': 'report.docx', 'artifact_sha256': self.sha('report.docx'), 'location': '候选设计', 'quote': quote}

    def audit(self):
        self.write('report-quality-review.json', self.receipt)
        return audit_quality(self.root, self.manifest)

    def test_concrete_algorithm_evidence_and_three_line_table(self):
        self.assertEqual(self.audit()['errors'], [])
        self.assertEqual(docx_style(self.root / 'report.docx'), [])

    def test_monochrome_missing_dossier_still_fails(self):
        self.receipt['technical_dossiers'] = []
        result = self.audit()
        self.assertEqual(result['style_status'], 'PASS')
        self.assertEqual(result['technical_status'], 'NEEDS_REVISION')

    def test_tiny_quote_is_not_complete_paragraph_evidence(self):
        self.dossier['mechanism']['quote'] = '斜率'
        self.assertTrue(self.audit()['technical_errors'])

    def test_malformed_receipt_returns_errors(self):
        self.receipt = []
        self.assertEqual(self.audit()['technical_status'], 'NEEDS_REVISION')

    def test_null_protocol_container_returns_errors(self):
        self.record['models_and_tests'] = None
        self.write('research-record.json', self.record)
        self.assertEqual(self.audit()['technical_status'], 'NEEDS_REVISION')

    def test_docx_missing_document_part_returns_errors(self):
        with zipfile.ZipFile(self.root / 'report.docx', 'w') as archive:
            archive.writestr('unrelated.xml', '<x/>')
        self.assertEqual(self.audit()['style_status'], 'FAIL')

    def test_recorded_evidence_does_not_certify_review_honesty(self):
        # A dishonest reviewer can give generic answers while retaining valid
        # anchors. The output must not label this engineering/semantic PASS.
        for key in ('trace_example', 'distinguish_failure', 'reproduce_test'):
            self.dossier['reader_review'][key]['answer'] = '已检查符合要求'
        result = self.audit()
        self.assertEqual(result['technical_status'], 'EVIDENCE_RECORDED')
        self.assertIn('no proof of engineering validity', result['scope'])

    def test_monochrome_gradient_forbidden(self):
        (self.root / 'mechanism.svg').write_text(self.svg.replace('</defs>', '<linearGradient id="g"><stop stop-color="#fff"/><stop stop-color="#000"/></linearGradient></defs>'), encoding='utf-8')
        self.assertTrue(svg_style(self.root / 'mechanism.svg'))

    def test_inherited_red_text_in_docx_is_rejected(self):
        path = self.root / 'report.docx'
        with zipfile.ZipFile(path) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        parts['word/styles.xml'] = parts['word/styles.xml'].replace(b'<w:rPrDefault><w:rPr>', b'<w:rPrDefault><w:rPr><w:color w:val="FF0000"/>')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, payload in parts.items():
                archive.writestr(name, payload)
        self.assertTrue(any('inherited' in e for e in docx_style(path)))

    def test_each_required_section_cannot_be_omitted(self):
        for section in SECTIONS:
            with self.subTest(section=section):
                old = self.dossier.pop(section)
                self.assertTrue(self.audit()['technical_errors'])
                self.dossier[section] = old

    def test_each_required_report_section_cannot_be_omitted(self):
        for section in GLOBAL_SECTIONS:
            with self.subTest(section=section):
                old = self.receipt['report_sections'].pop(section)
                self.assertTrue(self.audit()['technical_errors'])
                self.receipt['report_sections'][section] = old

    def test_stale_review_hash_rejected(self):
        self.dossier['mechanism']['artifact_sha256'] = '0' * 64
        self.assertTrue(self.audit()['technical_errors'])

    def test_explanation_only_in_receipt_rejected(self):
        self.dossier['mechanism']['quote'] = '新增完整公式只写在复核收据里，正文没有。'
        self.assertTrue(self.audit()['technical_errors'])

    def test_blanket_pass_is_not_reader_review(self):
        self.dossier['reader_review'] = {'status': 'reviewed', 'findings': ['已检查全部通过']}
        self.assertTrue(self.audit()['technical_errors'])

    def test_exploratory_route_cannot_escape_coverage(self):
        self.record['routes'].append({'id': 'R2', 'role': 'exploratory'})
        self.write('research-record.json', self.record)
        self.assertTrue(any('R2' in e for e in self.audit()['technical_errors']))

    def test_architecture_not_electrical_mechanism(self):
        self.dossier['domain'] = 'electrical'
        self.assertTrue(any('equivalent-circuit' in e for e in self.audit()['technical_errors']))

    def test_electrical_procurement_accepts_interface_evidence(self):
        self.dossier['domain'] = 'electrical'
        self.dossier['design_kind'] = 'procurement'
        self.dossier['diagram']['kind'] = 'product-interface'
        self.assertEqual(self.audit()['technical_errors'], [])

    def test_thermal_fluid_balance_diagram_supported(self):
        for domain in ('thermal', 'fluid'):
            self.dossier['domain'] = domain
            self.dossier['diagram']['kind'] = 'balance-network'
            self.assertEqual(self.audit()['technical_errors'], [])

    def test_open_reader_issue_blocks_completion(self):
        self.dossier['reader_review']['open_issues'] = ['缺少干扰反例']
        self.assertTrue(self.audit()['technical_errors'])

    def test_protocol_cannot_be_empty_or_borrowed_from_other_route(self):
        self.record['models_and_tests']['protocols'][0]['route_ids'] = ['R2']
        self.write('research-record.json', self.record)
        self.assertTrue(any('protocol' in e for e in self.audit()['technical_errors']))

    def test_actual_color_rejected_even_with_good_receipt(self):
        (self.root / 'mechanism.svg').write_text(self.svg.replace('fill="#fff"', 'fill="#00aaff"'), encoding='utf-8')
        result = self.audit()
        self.assertEqual(result['technical_status'], 'EVIDENCE_RECORDED')
        self.assertEqual(result['style_status'], 'FAIL')

    def test_css_color_and_arrow_marker_colors_checked(self):
        for addition in ('<style>rect { fill: red; }</style>', '<defs><marker><path fill="#f00"/></marker></defs>'):
            (self.root / 'mechanism.svg').write_text(self.svg.replace('</svg>', addition + '</svg>'), encoding='utf-8')
            self.assertTrue(svg_style(self.root / 'mechanism.svg'))

    def test_arrow_defs_do_not_count_as_mechanism(self):
        errors, warnings = [], []
        _check_svg(self.root / 'mechanism.svg', {'id': 'FIG1', 'figure_type': 'F4-mechanism-section'}, errors, warnings)
        self.assertTrue(any('box-only' in warning for warning in warnings))
        # A rectangle-based real circuit can be valid: this is a review warning,
        # never a geometry-count proof or an automatic physics rejection.
        self.assertEqual(errors, [])

    def test_recolored_grid_still_rejected(self):
        path = self.root / 'report.docx'
        with zipfile.ZipFile(path) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        parts['word/document.xml'] = parts['word/document.xml'].replace(b'<w:insideV w:val="nil"/>', b'<w:insideV w:val="single" w:color="000000"/>')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, payload in parts.items():
                archive.writestr(name, payload)
        self.assertTrue(any('grid' in e for e in docx_style(path)))

    def test_bound_table_renders_explicit_empty_list_text(self):
        record = copy.deepcopy(self.record)
        record['routes'][0]['innovation_attribution'] = {
            'mature_technology_status': 'none_identified',
            'mature_existing_technology': '本次未识别可直接集成的成熟技术',
            'existing_technology_source_ids': [],
            'scenario_integration': '按目标场景保留候选接口适配',
            'candidate_innovation': '无新增创新主张',
            'innovation_boundary': '通用原理不属于本项目创新',
            'validation_needed': '继续检索并验证候选路线',
        }
        self.write('bound-record.json', record)
        source = {
            'schema_version': '1.3',
            'research_record_path': 'bound-record.json',
            'research_record_sha256': self.sha('bound-record.json'),
            'title': '创新归属空来源渲染',
            'sections': [{
                'title': '技术构成与创新归属',
                'blocks': [{
                    'type': 'table',
                    'table_ref': '/routes',
                    'columns': [
                        {'header': '路线', 'field': 'id'},
                        {'header': '成熟技术来源', 'field': 'innovation_attribution/existing_technology_source_ids',
                         'join': '、', 'empty_text': '未列出；以成熟技术判定为准'},
                    ],
                }],
            }],
        }
        self.write('bound-source.json', source)
        build_report(self.root / 'bound-source.json', self.root / 'bound-report.docx')
        with zipfile.ZipFile(self.root / 'bound-report.docx') as archive:
            xml = archive.read('word/document.xml').decode('utf-8')
        self.assertIn('未列出；以成熟技术判定为准', xml)

    def test_generator_rejects_empty_cells_instead_of_empty_table(self):
        source = json.loads((self.root / 'source.json').read_text(encoding='utf-8'))
        source['sections'][0]['blocks'][-1]['rows'] = [['R1', '']]
        self.write('broken.json', source)
        with self.assertRaisesRegex(ValueError, 'blank cells'):
            build_report(self.root / 'broken.json', self.root / 'broken.docx')
        self.assertFalse((self.root / 'broken.docx').exists())

    def test_generator_never_silently_truncates_or_pads_rows(self):
        source = json.loads((self.root / 'source.json').read_text(encoding='utf-8'))
        for row in (['R1'], ['R1', '20', '%']):
            source['sections'][0]['blocks'][-1]['rows'] = [row]
            self.write('broken.json', source)
            with self.assertRaisesRegex(ValueError, 'never truncate or pad'):
                build_report(self.root / 'broken.json', self.root / 'broken.docx')

    def test_generator_preserves_long_protocol_and_explicit_unknown(self):
        source = json.loads((self.root / 'source.json').read_text(encoding='utf-8'))
        long_text = '完整步骤和单位必须保留。' * 25 + '每组合至少10次重复；停止条件是异常发热。'
        source['sections'][0]['blocks'][-1]['rows'] = [[long_text, '未知：待取得现场资料']]
        self.write('long.json', source)
        build_report(self.root / 'long.json', self.root / 'long.docx')
        with zipfile.ZipFile(self.root / 'long.docx') as archive:
            xml = archive.read('word/document.xml').decode('utf-8')
        self.assertIn(long_text, xml)
        self.assertIn('未知：待取得现场资料', xml)

    def test_actual_docx_blank_cell_detected(self):
        path = self.root / 'report.docx'
        with zipfile.ZipFile(path) as archive:
            parts = {name: archive.read(name) for name in archive.namelist()}
        parts['word/document.xml'] = parts['word/document.xml'].replace('H: 10,9,8'.encode(), b'')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, payload in parts.items():
                archive.writestr(name, payload)
        self.assertTrue(any('blank cell' in error for error in docx_style(path)))

    def test_legacy_complete_fails_without_strict_even_if_structure_passes(self):
        # Tests public routing after an independently successful structure check;
        # actual historical report integration is also checked outside fixtures.
        for strict in (False, True):
            with patch.object(delivery, '_validate_v11', return_value={'status': 'PASS', 'errors': [], 'warnings': []}):
                result = delivery.validate(self.root, {'schema_version': '1.1', 'status': 'complete'}, strict)
            self.assertEqual(result['status'], 'FAIL')
            self.assertIn('legacy schema', result['errors'][0])

    def test_legacy_stage_draft_is_explicitly_unchecked(self):
        with patch.object(delivery, '_validate_v11', return_value={'status': 'PASS', 'errors': [], 'warnings': []}):
            result = delivery.validate(self.root, {'schema_version': '1.1', 'status': 'degraded'})
        self.assertEqual(result['status'], 'LEGACY_UNCHECKED')
        self.assertEqual(result['errors'], [])

    def test_canonical_terms_roundtrip_and_bind_to_actual_word(self):
        source = json.loads((self.root / 'source.json').read_text(encoding='utf-8'))
        source['schema_version'] = '1.3'
        source['sections'][0]['blocks'].append({'type': 'paragraph', 'text_template': '[[triz_parameter:27]]；[[triz_parameter:28]]；[[triz_parameter:36]]。[[evidence_legend]]'})
        self.write('canonical.json', source)
        build_report(self.root / 'canonical.json', self.root / 'canonical.docx')
        with zipfile.ZipFile(self.root / 'canonical.docx') as archive:
            xml = archive.read('word/document.xml').decode('utf-8')
        for expected in ('#27 可靠性', '#28 测量精度', '#36 装置复杂性', 'M 受控实测', 'S 可追溯外部来源'):
            self.assertIn(expected, xml)
        self.assertEqual(verify_docx_bindings(self.root / 'canonical.docx', self.root / 'canonical.json')['status'], 'PASS')

    def test_invalid_canonical_parameter_is_not_invented(self):
        for token in ('0', '40', '测量精度'):
            with self.assertRaises(ValueError):
                canonical_text('[[triz_parameter:' + token + ']]')


if __name__ == '__main__':
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(QualityTests))
    if not result.wasSuccessful():
        raise SystemExit(2)
    print('REPORT_QUALITY_SELF_TEST_PASS tests=' + str(result.testsRun))
