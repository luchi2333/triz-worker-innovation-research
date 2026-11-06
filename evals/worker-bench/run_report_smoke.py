#!/usr/bin/env python3
"""Generate three-domain teaching reports and both reader entries, without model or research claims.

Use --libreoffice to produce PDFs/pages. Review scaffolds intentionally stay pending.
"""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'triz-worker-innovation-research/scripts'))
from run_engineering_examples import run
from research_review import draft_review, audit_review
from research_contract import digest
from build_figures import build_figures
from build_report import build_report
from report_bindings import verify_docx_bindings
from render_smoke import render


def generate(output, libreoffice=None):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('use a new smoke output directory')
    run(output)
    record_path = output/'research-record.json'
    record = json.loads(record_path.read_text(encoding='utf-8'))
    record['quality_review'] = draft_review(record, ['CLM-DOMAIN-1', 'CLM-DOMAIN-2', 'CLM-DOMAIN-3'])
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    build_figures(record_path, output/'figures')
    source_path = output/'report-source.json'
    source = json.loads(source_path.read_text(encoding='utf-8'))
    source['research_record_sha256'] = digest(record_path)
    source['quality_review_surface'] = True
    source_path.write_text(json.dumps(source, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    receipts = []
    for profile in ('base', 'engineering_review', 'award_defense'):
        candidate = dict(source)
        if profile != 'base':
            ids = ['CLM-DOMAIN-2', 'CLM-DOMAIN-1', 'CLM-DOMAIN-3'] if profile == 'engineering_review' else ['CLM-EX', 'CLM-DOMAIN-3', 'CLM-DOMAIN-2']
            candidate['reader_entry'] = {'profile': profile, 'claim_refs': ['/claims/'+cid for cid in ids]}
        path = output/(profile+'-source.json')
        path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        docx = output/(profile+'.docx')
        build_report(path, docx)
        receipt = {'profile': profile, 'docx': docx.name,
                   'bindings': verify_docx_bindings(docx, path), 'render': 'not_requested'}
        if libreoffice:
            receipt['render'] = render(docx, output/(profile+'-pages'), libreoffice, max_pages=0)
        receipts.append(receipt)
    # Replace the original example report as its record changed; keep no stale receipt.
    build_report(source_path, output/'engineering-examples.docx')
    result = {'kind': 'teaching_smoke_only', 'reports': receipts,
              'review_scaffold': audit_review(record), 'visual_review': 'pending',
              'formal_evaluation': False, 'field_measurements': False}
    (output/'example-receipt.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--libreoffice')
    args = parser.parse_args()
    result = generate(args.output, args.libreoffice)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2 if any(r['bindings']['status'] != 'PASS' or isinstance(r['render'], dict) and r['render']['errors'] for r in result['reports']) else 0)
