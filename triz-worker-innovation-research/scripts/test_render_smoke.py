"""Optional renderer guards. CI render job supplies PyMuPDF; core package needs only stdlib."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
try:
    import fitz
except ImportError:
    fitz = None
from build_report import build_report
from research_contract import digest
from render_smoke import inspect_pdf


@unittest.skipUnless(fitz, 'Optional PyMuPDF absent; rendering CI installs it')
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def pdf(self, name, texts):
        path = self.root/(name+'.pdf')
        with fitz.open() as document:
            for text in texts:
                page = document.new_page(width=400, height=200)
                if text:
                    page.insert_text((20, 40), text)
            document.save(path)
        return path

    def test_full_report_override_preserves_example_cap(self):
        pdf = self.pdf('long', ['Synthetic pagination fixture']*13)
        self.assertEqual(inspect_pdf(pdf, self.root/'limited')['status'], 'FAIL')
        self.assertEqual(inspect_pdf(pdf, self.root/'full', max_pages=0)['status'], 'RENDER_SMOKE_PASS')

    def test_missing_body_cannot_pass_on_render_success(self):
        source = self.root/'source.json'
        (self.root/'record.json').write_text('{"schema_version":"1.0"}', encoding='utf-8')
        source.write_text(json.dumps({'schema_version':'1.2','title':'Renderer fixture','cover_page':False,
                                      'research_record_path':'record.json',
                                      'research_record_sha256':digest(self.root/'record.json'),
                                      'sections':[{'title':'','blocks':[{'type':'paragraph','text':'Traceable test paragraph'}]}]}), encoding='utf-8')
        docx = self.root/'report.docx'; build_report(source, docx)
        good = self.pdf('good', ['Renderer fixture\nTraceable test paragraph'])
        self.assertEqual(inspect_pdf(good, self.root/'good-pages', docx)['docx_text_coverage']['status'], 'PASS')
        bad = self.pdf('bad', ['Renderer fixture'])
        receipt = inspect_pdf(bad, self.root/'bad-pages', docx)
        self.assertEqual(receipt['status'], 'FAIL')
        self.assertEqual(receipt['docx_text_coverage']['missing_excerpts'], ['Traceable test paragraph'])

    def test_blank_pages_remain_blocked_without_page_cap(self):
        receipt = inspect_pdf(self.pdf('blank', ['']), self.root/'blank-pages', max_pages=0)
        self.assertIn('page 1: likely blank', receipt['errors'])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RenderTests))
    if result.wasSuccessful():
        print('RENDER_GUARD_SELF_TEST_PASS', result.testsRun, 'skipped', len(result.skipped))
    raise SystemExit(0 if result.wasSuccessful() else 2)
