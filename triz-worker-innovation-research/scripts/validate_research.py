#!/usr/bin/env python3
"""Check a working record, explicitly complete a stage, or report change impacts.

python scripts/validate_research.py --record research-record.json
python scripts/validate_research.py --record research-record.json --complete-stage G0
python scripts/validate_research.py --record research-record.json --previous previous-record.json
python scripts/validate_research.py --record old-record.json --migrate upgraded-record.json
No invocation grants field authorization or mutates the source record.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from research_contract import STAGES, TRACE_COLLECTIONS, audit_record, change_impact


def migrate(record):
    result=copy.deepcopy(record)
    if result.get("schema_version") not in {"1.0","1.1"}:raise ValueError("unsupported record schema")
    previous=result["schema_version"];result["schema_version"]="1.1"
    for name in TRACE_COLLECTIONS:result.setdefault(name,[])
    result.setdefault("workflow",{"current_stage":"G0","completed_stage":None,"next_actions":[],"pending_questions":[],"authorization":"needs-recording"})
    result.setdefault("models_and_tests",{}).setdefault("protocols",[])
    if previous=="1.0":result.setdefault("migration_notes",[]).append("1.0 to 1.1: original values preserved; input/requirement/mechanism links and authorization must be populated from original evidence.")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record',type=Path,required=True);parser.add_argument('--previous',type=Path)
    parser.add_argument('--complete-stage',choices=STAGES);parser.add_argument('--migrate',type=Path)
    args=parser.parse_args()
    try:
        record=json.loads(args.record.read_text(encoding='utf-8'))
        if args.migrate:
            if args.migrate.resolve()==args.record.resolve() or args.migrate.exists():raise ValueError('migration output must be a new file')
            result=migrate(record);args.migrate.parent.mkdir(parents=True,exist_ok=True)
            args.migrate.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'migrated':str(args.migrate),'review_required':True}));return 0
        if args.complete_stage:
            record=copy.deepcopy(record);record.setdefault('workflow',{})['completed_stage']=args.complete_stage
        result=audit_record(record,root=args.record.resolve().parent)
        if args.previous:result['change_impact']=change_impact(json.loads(args.previous.read_text(encoding='utf-8')),record)
        result['status']='FAIL' if result['errors'] else 'PASS'
        print(json.dumps(result,ensure_ascii=False,indent=2));return 2 if result['errors'] else 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'status':'FAIL','errors':[str(exc)]},ensure_ascii=False));return 2


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
