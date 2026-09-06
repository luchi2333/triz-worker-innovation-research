#!/usr/bin/env python3
"""Generate an explicitly hypothetical mechanical tutorial using the installed skill.

python scripts/run_tutorial.py --output <new-directory> [--png-browser <executable>]
Output is a teaching report, not a field research result or manufacturing drawing.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode=True
from research_contract import audit_record, digest
from build_figures import build_figures
from build_report import build_report

ROOT=Path(__file__).resolve().parent.parent


def run(output, browser=None):
    output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise ValueError('tutorial output must be a new or empty directory')
    output.mkdir(parents=True,exist_ok=True)
    record=output/'research-record.json';shutil.copyfile(ROOT/'assets/tutorial-record.json',record)
    parsed=json.loads(record.read_text(encoding='utf-8'));audit=audit_record(parsed,root=output)
    if audit['errors']:raise ValueError('; '.join(audit['errors']))
    figures=build_figures(record,output/'figures',browser)
    source=json.loads((ROOT/'assets/tutorial-report-source.json').read_text(encoding='utf-8'))
    source['research_record_sha256']=digest(record)
    source_path=output/'report-source.json';source_path.write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
    report=build_report(source_path,output/'tutorial-report.docx')
    receipt={'tutorial':True,'record_check':audit,'figure_count':len(figures['figures']),'report':report,
             'engineering_review':'not-performed','visual_review':'pending','field_measurements':False}
    (output/'tutorial-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    return receipt


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--png-browser');args=parser.parse_args()
    try:result=run(args.output,args.png_browser)
    except (ValueError,OSError,TypeError,KeyError,subprocess.TimeoutExpired) as exc:print(json.dumps({'status':'FAIL','errors':[str(exc)]},ensure_ascii=False));raise SystemExit(2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
