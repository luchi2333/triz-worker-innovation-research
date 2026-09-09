"""Adversarial engineering consistency cases; synthetic, no field measurements."""
import sys
sys.dont_write_bytecode=True
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from engineering_checks import comparable, benefit_with_units
from build_figures import render_figure
from figure_readability import svg_font_points
from run_engineering_examples import examples
from package_release import package
from update_skill import checked_archive, upstream, extract, inventory


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_scaled_units(self):
        model={'formula_type':'linear_difference_rate','inputs':{'baseline':60,'candidate':.5,'quantity':100,'unit_rate':20},
               'input_units':{'baseline':'min/count','candidate':'h/count','quantity':'count/year','unit_rate':'CNY/h'},'unit':'CNY/year'}
        self.assertAlmostEqual(benefit_with_units(model),1000)
        model['unit']='h/year'
        with self.assertRaisesRegex(ValueError,'dimension mismatch'):benefit_with_units(model)

    def test_wrong_rate_unit(self):
        model={'formula_type':'linear_difference_rate','inputs':{'baseline':30,'candidate':20,'quantity':100,'unit_rate':20},
               'input_units':{'baseline':'min/count','candidate':'min/count','quantity':'count','unit_rate':'CNY'},'unit':'CNY'}
        with self.assertRaisesRegex(ValueError,'dimension mismatch'):benefit_with_units(model)

    def test_unknown_unit_is_not_guessed(self):
        with self.assertRaises(NotImplementedError):benefit_with_units({'formula_type':'net_benefit','unit':'workday','inputs':{'benefits':[],'costs':[]}})

    def comparison(self):
        protocol={'scope':'full_process','sampling_plan':'paired batch','metrics':[{'id':'TIME','unit':'s'}],
                  'comparison_basis':{'object_population':'lot A','metric_definition':'start to inspected finish','reference_points':'ports A/B',
                                      'instrument_chain':'clock CAL-1'},'condition_tolerances':{'temperature_C':1}}
        candidate={'id':'T1','route_id':'R1','protocol_id':'P1','comparison_conditions':{'temperature_C':20},'comparison_rationale':'Paired same lot; only route differs.'}
        baseline={'id':'T0','route_id':'R0','protocol_id':'P0','target_kind':'baseline_system','comparison_conditions':{'temperature_C':20.5}}
        return candidate,baseline,{'P1':protocol,'P0':copy.deepcopy(protocol)}

    def test_comparable_baseline(self):
        self.assertEqual(comparable(*self.comparison()),[])

    def test_wrong_baseline_metric_instrument_and_object(self):
        for key in ('object_population','instrument_chain','reference_points','metric_definition'):
            a,b,p=self.comparison();p['P0']['comparison_basis'][key]='other'
            self.assertTrue(comparable(a,b,p),key)
        a,b,p=self.comparison();p['P0']['metrics'][0]['unit']='min'
        self.assertTrue(comparable(a,b,p))

    def test_condition_mismatch_and_cycles(self):
        a,b,p=self.comparison();b['comparison_conditions']['temperature_C']=40
        self.assertTrue(comparable(a,b,p))
        a,b,p=self.comparison();b['baseline_test_id']='T1'
        self.assertTrue(comparable(a,b,p))

    def test_domain_examples_render(self):
        for spec in examples():
            svg,size=render_figure(spec,{})
            self.assertIn('data-',svg)
            target=self.root/(spec['id']+'.svg');target.write_text(svg,encoding='utf-8')
            self.assertGreater(svg_font_points(target,450,450*size['height']/size['width']),6)
            self.assertLess(svg_font_points(target,100,100*size['height']/size['width']),6)

    def test_node_misconnection(self):
        spec=examples()[0];spec['semantic_diagram']['elements'][0]['a']='NONEXISTENT'
        with self.assertRaisesRegex(ValueError,'unresolved'):render_figure(spec,{})

    def test_dangling_port(self):
        spec=examples()[0];spec['semantic_diagram']['elements']=[e for e in spec['semantic_diagram']['elements'] if e['id']!='S1']
        with self.assertRaisesRegex(ValueError,'dangling'):render_figure(spec,{})

    def test_contact_must_touch(self):
        spec=examples()[1];spec['semantic_diagram']['relations'][0]['a']=[479,188]
        with self.assertRaisesRegex(ValueError,'boundary|touch'):render_figure(spec,{})

    def test_label_overlap_and_overflow(self):
        for pos in ([24,195],[1010,190]):
            spec=examples()[0];spec['semantic_diagram']['elements'][1]['label_at']=pos
            with self.assertRaisesRegex(ValueError,'label'):render_figure(spec,{})

    def test_svg_scale_and_unit_conversion(self):
        path=self.root/'scale.svg'
        path.write_text('<svg viewBox="0 0 1000 500"><g transform="scale(0.25)"><text font-size="20pt">X</text></g></svg>')
        self.assertAlmostEqual(svg_font_points(path,500,250),20*96/72*.25*.5)

    def release_fixture(self):
        source=self.root/'skill';source.mkdir()
        (source/'SKILL.md').write_text('---\nname: triz-worker-innovation-research\nmetadata:\n  version: "2.9.0"\n---\n')
        manifest=package(source,self.root/'release','a'*40)
        remote={'channel':'stable','version':'2.9.0','commit':'a'*40,'release_ready':True,
                'archive_url':'https://github.com/luchi2333/triz-worker-innovation-research/releases/download/v2.9.0/'+manifest['archive'],
                'manifest_url':'https://github.com/luchi2333/triz-worker-innovation-research/releases/download/v2.9.0/release-manifest.json'}
        return source,manifest,remote,(self.root/'release'/manifest['archive']).read_bytes()

    def test_release_roundtrip_and_hash(self):
        source,manifest,remote,blob=self.release_fixture()
        with patch('update_skill.fetch',side_effect=[json.dumps(manifest).encode(),blob]):
            payload,checked=checked_archive(remote)
        target=self.root/'extracted';target.mkdir();extract(payload,target)
        self.assertEqual(inventory(target),checked['files'])
        with patch('update_skill.fetch',side_effect=[json.dumps(manifest).encode(),blob+b'tamper']):
            with self.assertRaisesRegex(ValueError,'checksum'):checked_archive(remote)

    def test_release_missing_assets_no_main_fallback(self):
        with patch('update_skill.fetch') as request:
            with self.assertRaisesRegex(ValueError,'no automatic main fallback'):checked_archive({'channel':'stable'})
            request.assert_not_called()

    def test_stable_channel_rejects_prerelease(self):
        with patch('update_skill.fetch',return_value=b'{"tag_name":"v2.9.0","prerelease":true}'):
            with self.assertRaisesRegex(ValueError,'stable'):upstream()


if __name__=='__main__':
    result=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if result.wasSuccessful():print('ENGINEERING_SELF_TEST_PASS',result.testsRun)
    raise SystemExit(0 if result.wasSuccessful() else 2)
