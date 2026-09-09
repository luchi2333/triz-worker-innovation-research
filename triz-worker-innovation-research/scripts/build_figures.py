#!/usr/bin/env python3
"""Render record-owned engineering geometry to SVG, optional PNG, and an HTML explainer.

python scripts/build_figures.py --record research-record.json --output figures
python scripts/build_figures.py --record research-record.json --output figures --png-browser <chromium-executable>
Geometry is authored for the actual mechanism; this renderer does not invent a design.
"""
from __future__ import annotations
import argparse
import ast
import html
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode=True
from research_contract import digest, fill_text, number, scalar
from build_report import FIGURE_TYPES
from engineering_diagrams import render_semantic

ROOT=Path(__file__).resolve().parent.parent
COLORS={'structure':'#e4e4e4','active':'#bebebe','object':'#d4d4d4','hypothesis':'#f0f0f0','danger':'#4b4b4b','white':'#ffffff','ink':'#333333','motion':'#535353'}


def expression(value, parameters):
    if isinstance(value,(float,int)):return number(value)
    if not isinstance(value,dict) or set(value)!={'expr'} or not isinstance(value['expr'],str):
        raise ValueError('geometry values must be numbers or {expr: arithmetic using parameter symbols}')
    if len(value['expr'])>500:raise ValueError('geometry expression too long')
    tree=ast.parse(value['expr'],mode='eval')
    def evaluate(node):
        if isinstance(node,ast.Expression):return evaluate(node.body)
        if isinstance(node,ast.Constant):return number(node.value)
        if isinstance(node,ast.Name) and node.id in parameters:return number(parameters[node.id])
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return evaluate(node.operand)*(1 if isinstance(node.op,ast.UAdd) else -1)
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b=evaluate(node.left),evaluate(node.right)
            if isinstance(node.op,ast.Add):return number(a+b)
            if isinstance(node.op,ast.Sub):return number(a-b)
            if isinstance(node.op,ast.Mult):return number(a*b)
            if b==0:raise ValueError('division by zero in geometry')
            return number(a/b)
        raise ValueError('unsupported geometry expression; only + - * / and known symbols are allowed')
    return number(evaluate(tree))


def primitive_svg(item, parameters, record, prefix, component_ids):
    if not isinstance(item,dict):raise ValueError('primitive must be an object')
    kind=item.get('kind');attrs=[]
    def n(key,default=None):
        value=expression(item.get(key,default),parameters)
        if abs(value)>100000:raise ValueError('geometry coordinate out of renderer bounds')
        return scalar(value)
    component=item.get('component_id')
    if component:
        if component not in component_ids:raise ValueError('unresolved figure component_id: '+component)
        attrs.append('data-component="'+html.escape(component,quote=True)+'"')
    semantic=item.get('semantic','structure')
    if semantic not in COLORS:raise ValueError('unknown semantic color: '+str(semantic))
    stroke=COLORS['danger'] if semantic=='danger' else COLORS['ink']
    attrs += [f'stroke="{stroke}"',f'stroke-width="{n("stroke_width",2)}"']
    if item.get('evidence_status')=='H' or item.get('hidden') is True:attrs.append('stroke-dasharray="6 4"')
    base=' '.join(attrs)
    if kind in {'rect','circle'}:
        if kind=='rect':
            if expression(item.get('width'),parameters)<=0 or expression(item.get('height'),parameters)<=0:raise ValueError('rectangle dimensions must be positive')
            geo=f'x="{n("x")}" y="{n("y")}" width="{n("width")}" height="{n("height")}"'
        else:
            if expression(item.get('r'),parameters)<=0:raise ValueError('circle radius must be positive')
            geo=f'cx="{n("cx")}" cy="{n("cy")}" r="{n("r")}"'
        return f'<{kind} {geo} {base} fill="{COLORS[semantic]}"/>'
    if kind in {'line','arrow'}:
        arrow=f' marker-end="url(#{prefix}arrow)"' if kind=='arrow' else ''
        if item.get('double') and kind=='arrow':arrow+=f' marker-start="url(#{prefix}arrow)"'
        return f'<line x1="{n("x1")}" y1="{n("y1")}" x2="{n("x2")}" y2="{n("y2")}" {base}{arrow}/>'
    if kind=='polyline':
        points=item.get('points',[])
        if not isinstance(points,list) or len(points)<2:raise ValueError('polyline needs at least two points')
        coords=' '.join(f'{scalar(expression(p[0],parameters))},{scalar(expression(p[1],parameters))}' for p in points)
        return f'<polyline points="{coords}" {base} fill="none"/>'
    if kind=='text':
        size=expression(item.get('font_size',20),parameters)
        if size<14:raise ValueError('source diagram text must be at least 14 px; check final embedded size too')
        value,_=fill_text(item.get('text_template',item.get('text','')),record)
        for symbol,param_value in parameters.items():value=value.replace('${'+symbol+'}',scalar(param_value))
        anchor=item.get('anchor','start')
        if anchor not in {'start','middle','end'}:raise ValueError('invalid text anchor')
        return f'<text x="{n("x")}" y="{n("y")}" font-size="{scalar(size)}" fill="{COLORS["ink"]}" text-anchor="{anchor}">{html.escape(value)}</text>'
    raise ValueError('unsupported primitive kind: '+str(kind))


def render_figure(spec, record, frame_id=None):
    fid=spec.get('id','')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',fid):raise ValueError('figure ID must be filename-safe')
    for key in ['title','figure_type','main_message','claim_limit','purpose']:
        if not spec.get(key):raise ValueError(f'figure {fid} missing {key}')
    if spec.get('purpose') not in {'explanation','initial_design','detailed_design'}:raise ValueError('invalid drawing purpose')
    if spec.get('design_status') not in {'V0','V1','V2','V3'}:raise ValueError('figure maturity must be V0-V3')
    if spec.get('figure_type') not in FIGURE_TYPES:raise ValueError('unsupported engineering figure type')
    parameters={p['symbol']:p.get('value') for p in record.get('parameters',[]) if isinstance(p,dict) and p.get('symbol')}
    components={c.get('id') for r in record.get('routes',[]) if isinstance(r,dict) for c in r.get('components',[]) if isinstance(c,dict)}
    frames=spec.get('frames') or [{'id':'view','label':'','primitives':spec.get('primitives',[])}]
    if len({f.get('id') for f in frames})!=len(frames):raise ValueError('duplicate frame IDs')
    if spec.get('figure_type')=='F5-motion-sequence' and not 3<=len(frames)<=6:
        raise ValueError('motion sequence requires 3-6 recorded frames')
    if frame_id is not None:
        frames=[f for f in frames if f.get('id')==frame_id]
        if not frames:raise ValueError('unknown figure frame')
    width=number(spec.get('width',840));height=number(spec.get('height',480))
    if not 200<=width<=2400 or not 160<=height<=2400:raise ValueError('invalid figure panel size')
    columns=1 if frame_id is not None else min(int(spec.get('columns',1)),len(frames))
    if columns not in {1,2,3}:raise ValueError('figure columns must be 1..3')
    total_w=width*columns;total_h=height*math.ceil(len(frames)/columns)+92
    prefix=fid+'-'+(frame_id or 'all')+'-'
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:g}" height="{total_h:g}" viewBox="0 0 {total_w:g} {total_h:g}" role="img" aria-label="{html.escape(spec["title"],quote=True)}">',
           '<title>'+html.escape(spec['title'])+'</title>',
           '<desc>'+html.escape(spec['main_message']+' '+spec['claim_limit'])+'</desc>',
           '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}</style>',
           f'<defs><marker id="{prefix}arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="#535353"/></marker></defs>',
           f'<rect width="{total_w:g}" height="{total_h:g}" fill="white"/>',
           f'<text x="20" y="30" font-size="22" fill="#333333">{html.escape(spec["title"])}</text>']
    for index,frame in enumerate(frames):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',str(frame.get('id',''))):raise ValueError('frame ID must be filename-safe')
        local=parameters.copy()
        for key,value in frame.get('parameter_overrides',{}).items():
            if key not in local:raise ValueError('frame overrides unknown parameter: '+key)
            local[key]=expression(value,parameters)
        x=(index%columns)*width;y=44+(index//columns)*height
        parts.append(f'<g transform="translate({x:g} {y:g})"><rect x="2" y="2" width="{width-4:g}" height="{height-4:g}" fill="#f6f6f6" stroke="#dbdbdb"/>')
        if frame.get('label'):parts.append(f'<text x="14" y="29" font-size="19" fill="#333333">{html.escape(frame["label"])}</text>')
        semantic = frame.get('semantic_diagram',spec.get('semantic_diagram'))
        if semantic:
            parts.append(render_semantic(semantic,width,height,prefix,record))
        elif not frame.get('primitives',spec.get('primitives',[])):raise ValueError('each figure frame requires authored geometry')
        for item in frame.get('primitives',spec.get('primitives',[])):
            parts.append(primitive_svg(item,local,record,prefix,components))
        parts.append('</g>')
    footer=spec['design_status']+' · '+spec['claim_limit']
    parts.append(f'<text x="20" y="{total_h-16:g}" font-size="17" fill="#656565">{html.escape(footer)}</text></svg>')
    return ''.join(parts), {'width':total_w,'height':total_h}


def render_png(svg_path, png_path, browser, width, height):
    """Optional local Chromium executable; isolated profile, no shell interpolation."""
    executable=Path(browser).resolve()
    if not executable.is_file():raise ValueError('PNG browser executable does not exist')
    with tempfile.TemporaryDirectory(prefix='triz-render-') as tmp:
        temp=Path(tmp);page=temp/'figure.html'
        page.write_text('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:white}svg{display:block;width:100%;height:auto}</style>'+svg_path.read_text(encoding='utf-8'),encoding='utf-8')
        command=[str(executable),'--headless','--no-first-run','--disable-extensions','--hide-scrollbars',
                 '--force-device-scale-factor=1',f'--user-data-dir={temp / "profile"}',
                 f'--window-size={int(width)},{int(height)}',f'--screenshot={png_path.resolve()}',page.as_uri()]
        done=subprocess.run(command,capture_output=True,text=True,timeout=45)
        if not png_path.is_file():raise ValueError('PNG rendering failed: '+done.stderr[-500:])
        header=png_path.read_bytes()[:24]
        if header[:8]!=b'\x89PNG\r\n\x1a\n' or struct.unpack('>II',header[16:24])!=(int(width),int(height)):
            raise ValueError('rendered PNG dimensions do not match the planned canvas')


def build_figures(record_path, output, png_browser=None):
    record_path=Path(record_path).resolve();output=Path(output).resolve()
    # Keep generated paths portable relative to the research directory.
    output.relative_to(record_path.parent)
    record=json.loads(record_path.read_text(encoding='utf-8'));output.mkdir(parents=True,exist_ok=True)
    entries=[];pages=[];seen=set()
    for spec in record.get('figure_specs',[]):
        fid=spec.get('id')
        if fid in seen:raise ValueError('duplicate figure ID')
        seen.add(fid);svg,dimensions=render_figure(spec,record)
        path=output/(fid+'.svg');path.write_text(svg,encoding='utf-8')
        entry={k:spec.get(k) for k in ['id','title','figure_type','purpose','design_status','main_message','claim_limit','route_ids']}
        entry.update({'svg_path':path.relative_to(record_path.parent).as_posix(),'svg_sha256':digest(path),'dimensions':dimensions,'png_status':'not-rendered','visual_review':'pending'})
        if png_browser:
            png=output/(fid+'.png');render_png(path,png,png_browser,**dimensions)
            entry.update({'png_path':png.relative_to(record_path.parent).as_posix(),'png_sha256':digest(png),'png_status':'rendered'})
        frame_pages=[]
        for frame in spec.get('frames',[]):
            frame_svg,_=render_figure(spec,record,frame['id'])
            frame_pages.append({'id':frame['id'],'label':frame.get('label',''),'description':frame.get('description',''),'svg':frame_svg})
        pages.append({'id':fid,'title':spec['title'],'message':spec['main_message'],'limit':spec['claim_limit'],'svg':svg,'frames':frame_pages})
        entries.append(entry)
    if not entries:raise ValueError('record has no figure_specs; author geometry for the actual mechanism first')
    manifest={'schema_version':'1.0','research_record_sha256':digest(record_path),'figures':entries,'visual_review':'pending'}
    (output/'figure-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    template=(ROOT/'assets/report-explainer.html').read_text(encoding='utf-8')
    data={'title':record.get('project',{}).get('title','技术方案图解'),'maturity':record.get('project',{}).get('maturity','V0'),
          'parameters':record.get('parameters',[]),'figures':pages}
    payload=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    (output/'report-explainer.html').write_text(template.replace('__TRIZ_DATA__',payload),encoding='utf-8')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--png-browser')
    args=parser.parse_args()
    try:result=build_figures(args.record,args.output,args.png_browser)
    except (OSError,ValueError,TypeError,KeyError,SyntaxError,subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status':'FAIL','errors':[str(exc)]},ensure_ascii=False));return 2
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
