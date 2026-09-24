"""Compile record references and verify bound blocks in the actual DOCX XML."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
import zipfile

from research_contract import digest, fill_text, local_file, resolve_ref, scalar
from figure_readability import check_control_extent

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
EVIDENCE_LEGEND = '证据标记：F 现场报告事实；M 受控实测；S 可追溯外部来源（含厂家规格）；H 工程假设或推导。'


def document_text_hash(document):
    if isinstance(document,str):document=ET.fromstring(document)
    texts=[''.join(t.text or '' for t in p.iter(W+'t')) for p in document.iter(W+'p')]
    return hashlib.sha256(json.dumps(texts,ensure_ascii=False).encode('utf-8')).hexdigest()


def critical_literal(text):
    text=re.sub(r'\{\{[^{}]+\}\}|\[\[[^\]]+\]\]', '', text)
    return bool(re.search(r'\d+(?:\.\d+)?\s*(?:%|％|mm|cm|kV|mA|MΩ|kΩ|Ω|元|万元|秒|分钟|小时|人|次|件|端)\b|\d+(?:\.\d+)?\s*(?:%|％|元|万元|秒|分钟|小时)|\bV[0-3]\b|实测|已验证|零损伤|安全阈值|推荐路线',text))


def canonical_text(text):
    """Render vocabulary owned by the skill, never retyped by the report author."""
    text = text.replace('[[evidence_legend]]', EVIDENCE_LEGEND)
    def parameter(match):
        data = json.loads((Path(__file__).resolve().parent.parent / 'references/contradiction-matrix.json').read_text(encoding='utf-8'))
        raw = match.group(1)
        if not raw.isdigit():
            raise ValueError('TRIZ parameter reference must be an integer ID')
        item = next((p for p in data['parameters'] if p['id'] == int(raw)), None)
        if item is None:
            raise ValueError('TRIZ parameter reference must be 1..39')
        return f"#{item['id']} {item['zh']}"
    return re.sub(r'\[\[triz_parameter:([^\]]+)\]\]', parameter, text)


def compile_source(source, record, root):
    data=copy.deepcopy(source);bindings=[];figure_numbers={};figures={};critical_issues=[]
    if data.get('figure_manifest_path'):
        figure_path=local_file(root,data['figure_manifest_path'])
        payload=json.loads(figure_path.read_text(encoding='utf-8'))
        if payload.get('research_record_sha256')!=data.get('research_record_sha256'):
            raise ValueError('figures were generated from a different record; rebuild figures')
        for item in payload.get('figures',[]):
            if not isinstance(item,dict) or item.get('id') in figures:raise ValueError('duplicate/invalid figure manifest entry')
            for kind in ['svg','png']:
                if item.get(kind+'_path'):
                    path=local_file(root,item[kind+'_path'])
                    if digest(path)!=item.get(kind+'_sha256'):raise ValueError('figure hash mismatch: '+item['id'])
            figures[item['id']]=item
    # Assign one number per stable figure ID, including repeated previews.
    for section in data.get('sections',[]):
        for block in section.get('blocks',[]):
            fid=block.get('figure_ref') or block.get('figure_id')
            if block.get('type')=='figure' and fid and fid not in figure_numbers:figure_numbers[fid]=len(figure_numbers)+1
    narrative_blocks=0
    for si,section in enumerate(data.get('sections',[])):
        for bi,block in enumerate(section.get('blocks',[])):
            refs=[];expected=[];kind=block.get('type');bound=False
            if not block.get('claim_ref') and kind in {'paragraph','key_message','bullets','table'}:
                literal=json.dumps({k:v for k,v in block.items() if k in {'text','text_template','items','item_templates','rows'}},ensure_ascii=False)
                if critical_literal(literal) or block.get('fact_role') in {'performance','safety','maturity','recommendation','benefit','dimension'}:
                    # Templates may interpolate numbers, but a declared critical statement
                    # is owned in its entirety by a record claim.
                    critical_issues.append(f'sections/{si}/blocks/{bi}: critical fact needs claim_ref or record-owned table')
            def interpolate(text):
                nonlocal refs
                rendered,found=fill_text(canonical_text(text),record);refs.extend(found)
                def figure_link(match):
                    fid=match.group(1)
                    if fid not in figure_numbers:raise ValueError('unknown figure reference: '+fid)
                    return '图 '+str(figure_numbers[fid])
                return re.sub(r'\[\[figure:([A-Za-z][A-Za-z0-9_-]*)\]\]',figure_link,rendered)
            if kind in {'paragraph','key_message'}:
                if 'claim_ref' in block:
                    ref=block['claim_ref'];claim=resolve_ref(record,ref)
                    if not isinstance(claim,dict) or not claim.get('id'):raise ValueError('claim_ref must resolve a claim object')
                    text=claim.get('allowed_wording') if claim.get('evidence_status') in {'H','unknown',None} else claim.get('text')
                    if not text:raise ValueError('claim lacks wording allowed by its evidence status')
                    block['text']=f"[{claim['id']} · {claim.get('evidence_status','unknown')}] {text}"
                    refs.append(ref);bound=True
                elif 'text_template' in block:
                    block['text']=interpolate(block['text_template']);bound=True
                expected=[block.get('text','')]
            elif kind=='bullets' and 'item_templates' in block:
                block['items']=[interpolate(t) for t in block['item_templates']];bound=True
                expected=['• '+item for item in block['items']]
            elif kind=='table' and 'table_ref' in block:
                ref=block['table_ref'];items=resolve_ref(record,ref)
                if not isinstance(items,list):raise ValueError('table_ref must resolve an array')
                columns=block.get('columns',[])
                if not columns:raise ValueError('bound table requires columns')
                block['headers']=[c['header'] for c in columns];block['rows']=[]
                for item in items:
                    values=[]
                    for col in columns:
                        value=item
                        for key in col['field'].split('/'):
                            if not isinstance(value,dict) or key not in value:raise ValueError('unresolved bound table column')
                            value=value[key]
                        if isinstance(value,list) and 'join' in col:
                            if not value:raise ValueError('bound table list column cannot be empty')
                            value=str(col['join']).join(scalar(item) for item in value)
                        values.append(col.get('unknown_text','待确定') if value is None else scalar(value))
                    block['rows'].append(values)
                refs.append(ref);expected=block['headers']+[v for row in block['rows'] for v in row];bound=True
            elif kind=='figure' and 'figure_ref' in block:
                fid=block['figure_ref'];item=figures.get(fid)
                if not item:raise ValueError('figure_ref requires a matching generated figure manifest')
                spec=resolve_ref(record,'/figure_specs/'+fid)
                block.update({'figure_id':fid,'path':item.get('png_path') or item['svg_path'],
                              'caption':f"图 {figure_numbers[fid]}　{spec['title']}（{spec['design_status']}）",
                              'figure_type':spec['figure_type'],'design_status':spec['design_status'],
                              'main_message':spec['main_message'],'claim_limit':spec['claim_limit'],
                              'alt':spec.get('alt') or spec['main_message']})
                refs.append('/figure_specs/'+fid)
                expected=[block['caption'],'图示要点：'+block['main_message'],'证据边界：'+block['claim_limit']];bound=True
            if bound:
                bid=f'TRIZ-B{len(bindings)+1:04d}';block['_binding_id']=bid
                bindings.append({'id':bid,'source_location':f'sections/{si}/blocks/{bi}', 'refs':refs,'expected_texts':expected,'kind':kind,
                                 'svg_path':figures.get(block.get('figure_ref'),{}).get('svg_path'),
                                 'figure_sha256':digest(local_file(root,block['path'])) if kind=='figure' else None})
            elif kind not in {'page_break'}:narrative_blocks+=1
    data['_bindings']=bindings;data['_narrative_blocks']=narrative_blocks;data['_critical_issues']=critical_issues
    return data


def verify_docx_bindings(docx_path, source_path, require_critical=False):
    source_path=Path(source_path).resolve();source=json.loads(source_path.read_text(encoding='utf-8'))
    if source.get('schema_version')!='1.3':return {'status':'LEGACY_UNCHECKED','errors':[],'bound_blocks':0}
    record_path=local_file(source_path.parent,source.get('research_record_path'))
    if digest(record_path)!=source.get('research_record_sha256'):raise ValueError('report source refers to a stale research record')
    record=json.loads(record_path.read_text(encoding='utf-8'));compiled=compile_source(source,record,source_path.parent)
    errors=[]
    if require_critical or source.get('critical_facts_policy')=='bound':
        if source.get('critical_facts_policy')!='bound':errors.append('complete report requires critical_facts_policy=bound')
        errors.extend(compiled['_critical_issues'])
    with zipfile.ZipFile(docx_path) as package:
        document=ET.fromstring(package.read('word/document.xml'))
        source_hash=hashlib.sha256(source_path.read_bytes()).hexdigest()
        if 'customXml/triz-provenance.json' not in package.namelist():errors.append('DOCX missing generation provenance')
        else:
            provenance=json.loads(package.read('customXml/triz-provenance.json'))
            if provenance.get('document_text_sha256'):
                if provenance['document_text_sha256']!=document_text_hash(document):
                    errors.append('actual DOCX narrative differs from generated report; rebuild and review')
            elif require_critical:errors.append('complete report requires whole-text generation fingerprint')
            if provenance.get('research_record_sha256')!=digest(record_path) or provenance.get('report_source_sha256')!=source_hash:
                errors.append('DOCX provenance differs from current record/report source')
        controls={}
        for control in document.iter(W+'sdt'):
            tag=control.find(W+'sdtPr/'+W+'tag')
            if tag is not None:
                bid=tag.get(W+'val')
                if bid in controls:errors.append('duplicate DOCX binding: '+str(bid))
                controls[bid]=control
        for binding in compiled['_bindings']:
            control=controls.get(binding['id'])
            if control is None:errors.append('missing DOCX bound block: '+binding['id']);continue
            actual=[''.join(node.text or '' for node in paragraph.iter(W+'t')) for paragraph in control.iter(W+'p')]
            actual=[value for value in actual if value]
            expected=[value for value in binding['expected_texts'] if value]
            if actual!=expected:errors.append('actual DOCX text differs from record binding: '+binding['id'])
            if binding['figure_sha256']:
                if binding.get('svg_path'):
                    check_control_extent(control,local_file(source_path.parent,binding['svg_path']),errors)
                ns='{http://schemas.openxmlformats.org/drawingml/2006/main}'
                relns='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
                refs=[node.get(relns+'embed') for node in control.iter(ns+'blip')]
                relations=ET.fromstring(package.read('word/_rels/document.xml.rels'))
                targets={r.get('Id'):r.get('Target') for r in relations}
                if len(refs)!=1:errors.append('bound figure missing or duplicated: '+binding['id'])
                else:
                    target=targets.get(refs[0],'')
                    if not target.startswith('media/') or 'word/'+target not in package.namelist():errors.append('bound image relationship invalid')
                    elif hashlib.sha256(package.read('word/'+target)).hexdigest()!=binding['figure_sha256']:errors.append('actual DOCX image differs from bound figure: '+binding['id'])
        wanted={b['id'] for b in compiled['_bindings']}
        if set(controls)-wanted:errors.append('DOCX has unexpected bound blocks')
    return {'status':'FAIL' if errors else 'PASS','errors':errors,'bound_blocks':len(compiled['_bindings']),
            'unbound_narrative_blocks':compiled['_narrative_blocks'], 'critical_fact_issues':compiled['_critical_issues'],
            'scope':'Bound content and actual image extents checked; critical-language screening is heuristic, semantic completeness needs reader review.'}
