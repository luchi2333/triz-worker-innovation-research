"""Record-owned electrical topology and mechanical diagram symbols, SVG only.

Connections are authored engineering data. Geometry/graph checks cannot establish
physical correctness. No third-party symbol artwork is copied.
"""
import html
import math
import re


def esc(value): return html.escape(str(value), quote=True)


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('diagram coordinate must be finite')
    return float(value)


def point(value):
    if not isinstance(value, list) or len(value) != 2: raise ValueError('point requires x,y')
    return tuple(finite(v) for v in value)


def line(a, b, extra=''):
    return f'<line x1="{a[0]:g}" y1="{a[1]:g}" x2="{b[0]:g}" y2="{b[1]:g}" stroke="#111111" stroke-width="2" {extra}/>'


class Canvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.parts, self.labels = [], []

    def label(self, text, x, y, size=22):
        # Conservative bound for CJK/Latin, followed by actual browser/Word QA.
        width = sum(size if ord(c) > 255 else size * .62 for c in str(text))
        box = (x, y-size, x+width, y+size*.2)
        if x < 12 or y-size < 6 or box[2] > self.width-12 or box[3] > self.height-6:
            raise ValueError('diagram label outside panel: ' + str(text))
        for old in self.labels:
            if min(box[2], old[2]) > max(box[0], old[0]) and min(box[3], old[3]) > max(box[1], old[1]):
                raise ValueError('diagram labels overlap: ' + str(text))
        self.labels.append(box)
        self.parts.append(f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" fill="#111111">{esc(text)}</text>')

    def check_point(self, p):
        if not 8 <= p[0] <= self.width-8 or not 8 <= p[1] <= self.height-8:
            raise ValueError('diagram geometry outside panel')


def electrical(data, canvas):
    nodes, degrees, adjacency = {}, {}, {}
    for node in data.get('nodes', []):
        key = node['id']
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', key) or key in nodes: raise ValueError('invalid/duplicate node ID')
        pos = point(node['at']); canvas.check_point(pos)
        if pos in nodes.values(): raise ValueError('coincident nodes must share one ID')
        nodes[key], degrees[key], adjacency[key] = pos, 0, set()
    ids = set()
    parts = []
    kinds = {'wire', 'resistor', 'capacitor', 'switch', 'source', 'sensor', 'measurement_port', 'ground'}
    for element in data.get('elements', []):
        eid, kind = element['id'], element['kind']
        if eid in ids or kind not in kinds: raise ValueError('invalid/duplicate electrical element')
        ids.add(eid)
        a = element['a']
        if a not in nodes: raise ValueError('unresolved electrical port ' + a)
        if kind == 'ground':
            x, y = nodes[a]
            canvas.check_point((x-18, y+25));canvas.check_point((x+18,y+25))
            parts += [line((x,y),(x,y+8)), line((x-18,y+8),(x+18,y+8)),
                      line((x-12,y+16),(x+12,y+16)), line((x-6,y+24),(x+6,y+24))]
            degrees[a] += 1
        else:
            b = element['b']
            if b not in nodes or a == b: raise ValueError('invalid second electrical port')
            degrees[a] += 1; degrees[b] += 1
            adjacency[a].add(b); adjacency[b].add(a)
            x1,y1 = nodes[a];x2,y2 = nodes[b]
            dx,dy = x2-x1,y2-y1
            length = math.hypot(dx,dy)
            if kind == 'wire':
                points = [nodes[a]] + [point(p) for p in element.get('via', [])] + [nodes[b]]
                for p,q in zip(points,points[1:]):
                    canvas.check_point(p);canvas.check_point(q)
                    if p[0] != q[0] and p[1] != q[1]: raise ValueError('wire must use orthogonal segments')
                    # A wire cannot run through a different declared electrical node.
                    for nid,npos in nodes.items():
                        if nid not in {a,b} and ((p[0]==q[0]==npos[0] and min(p[1],q[1])<=npos[1]<=max(p[1],q[1])) or
                                                (p[1]==q[1]==npos[1] and min(p[0],q[0])<=npos[0]<=max(p[0],q[0]))):
                            raise ValueError('wire passes through undeclared junction: ' + nid)
                    parts.append(line(p,q))
            else:
                if length < 84 or (dx and dy): raise ValueError('component needs orthogonal ports at least 84 units apart')
                mid=length/2; angle=math.degrees(math.atan2(dy,dx))
                body = [line((0,0),(mid-24,0)),line((mid+24,0),(length,0))]
                if kind == 'resistor':
                    body.append(f'<rect x="{mid-24:g}" y="-11" width="48" height="22" fill="white" stroke="#111111" stroke-width="2"/>')
                elif kind == 'capacitor':
                    body += [line((mid-24,0),(mid-6,0)),line((mid+6,0),(mid+24,0)),line((mid-6,-20),(mid-6,20)),line((mid+6,-20),(mid+6,20))]
                elif kind == 'switch':
                    state=element.get('state')
                    if state not in {'open','closed'}: raise ValueError('switch requires explicit open/closed state')
                    body.append(line((mid-24,0),(mid+24,0 if state=='closed' else -20)))
                    body.append(f'<circle cx="{mid+24:g}" cy="0" r="3" fill="white" stroke="#111111"/>')
                else:
                    body.append(f'<circle cx="{mid:g}" cy="0" r="24" fill="white" stroke="#111111" stroke-width="2"/>')
                    if kind=='source':
                        body += [line((mid+4,-5),(mid+14,-5)),line((mid+9,-10),(mid+9,0)),line((mid-15,5),(mid-5,5))]
                    else:
                        body.append(f'<path d="M {mid-12} 10 L {mid+12} -10 M {mid+12} -10 L {mid+4} -10 M {mid+12} -10 L {mid+12} -2" fill="none" stroke="#111111" stroke-width="2"/>')
                parts.append(f'<g data-element="{esc(eid)}" data-kind="{kind}" data-a="{esc(a)}" data-b="{esc(b)}" transform="translate({x1:g} {y1:g}) rotate({angle:g})">'+''.join(body)+'</g>')
        if element.get('label'):
            x,y=point(element['label_at']);canvas.label(element['label'],x,y)
    allowed=set(data.get('open_nodes',[]))
    if not allowed <= set(nodes): raise ValueError('unknown declared open node')
    if any(degrees[n]<2 for n in nodes if n not in allowed): raise ValueError('unintended dangling electrical port')
    if not nodes: raise ValueError('electrical diagram requires nodes')
    visited, pending = set(), [next(iter(nodes))]
    while pending:
        n=pending.pop()
        if n not in visited: visited.add(n);pending.extend(adjacency[n]-visited)
    if visited != set(nodes): raise ValueError('disconnected circuit: split isolated domains into separate diagrams with explicit interfaces')
    for n, pos in nodes.items():
        if degrees[n] >= 3:
            parts.append(f'<circle data-junction="{esc(n)}" cx="{pos[0]:g}" cy="{pos[1]:g}" r="4" fill="#111111"/>')
    canvas.parts = parts + canvas.parts


def mechanical(data, canvas, prefix):
    bodies={}; parts=[]
    pattern=prefix+'section'
    parts.append(f'<defs><pattern id="{pattern}" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M-2 2L2 -2M0 10L10 0M8 12L12 8" stroke="#777777" stroke-width="1"/></pattern></defs>')
    for body in data.get('bodies',[]):
        bid=body['id']
        if bid in bodies: raise ValueError('duplicate mechanical body')
        x,y,w,h=[finite(v) for v in body['box']]
        if min(w,h)<=0: raise ValueError('body requires positive size')
        canvas.check_point((x,y));canvas.check_point((x+w,y+h));bodies[bid]=(x,y,w,h)
        fill=f'url(#{pattern})' if body.get('section') else 'white'
        parts.append(f'<rect data-body="{esc(bid)}" x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" stroke="#111111" stroke-width="2" fill="{fill}"/>')
        if body.get('label'): canvas.label(body['label'],*point(body['label_at']))
    def on_body(p,bid):
        if bid not in bodies: raise ValueError('unresolved mechanical body')
        x,y,w,h=bodies[bid];px,py=p
        return (x<=px<=x+w and (py==y or py==y+h)) or (y<=py<=y+h and (px==x or px==x+w))
    for item in data.get('relations',[]):
        kind=item['kind'];a=point(item['a']);b=point(item['b'])
        canvas.check_point(a);canvas.check_point(b)
        if a==b: raise ValueError('mechanical relation has zero length')
        if kind in {'contact','protected_surface','constraint'}:
            for p in (a,b):
                if not on_body(p,item['body']): raise ValueError('surface/constraint must lie on the referenced body boundary')
            if kind=='contact':
                for p in (a,b):
                    if not on_body(p,item['other_body']): raise ValueError('contact must touch both declared bodies')
            if kind=='protected_surface':
                parts.append(f'<line x1="{a[0]:g}" y1="{a[1]:g}" x2="{b[0]:g}" y2="{b[1]:g}" stroke="white" stroke-width="4"/>')
            parts.append(line(a,b,'stroke-dasharray="8 4"' if kind=='protected_surface' else ''))
            if kind=='constraint':
                parts += [line((a[0]-8,a[1]+8),a),line((b[0]-8,b[1]+8),b)]
        elif kind in {'force','motion'}:
            if item.get('body') not in bodies: raise ValueError('force/motion requires target body')
            parts.append(line(a,b,f'marker-end="url(#{prefix}arrow)"'))
        elif kind in {'dimension','clearance'}:
            if not item.get('label'): raise ValueError('dimension must name its parameter and evidence state')
            if a[0]!=b[0] and a[1]!=b[1]: raise ValueError('dimension requires aligned endpoints')
            parts.append(line(a,b,f'marker-start="url(#{prefix}arrow)" marker-end="url(#{prefix}arrow)"'))
            for x,y in (a,b):
                parts.append(line((x,y-10),(x,y+10)) if a[1]==b[1] else line((x-10,y),(x+10,y)))
        else: raise ValueError('unsupported mechanical relation')
        if item.get('label'):canvas.label(item['label'],*point(item['label_at']))
    if not bodies: raise ValueError('mechanical diagram requires bodies')
    canvas.parts=parts+canvas.parts


def render_semantic(data, width, height, prefix, record):
    from research_contract import fill_text
    import copy
    data=copy.deepcopy(data)
    def bind(value):
        if isinstance(value,dict):
            for k,v in list(value.items()):
                if k=='label_template':value['label']=fill_text(v,record)[0]
                else:bind(v)
        elif isinstance(value,list):
            for item in value:bind(item)
    bind(data)
    canvas=Canvas(width,height)
    domain=data.get('domain')
    if domain=='electrical':electrical(data,canvas)
    elif domain=='mechanical':mechanical(data,canvas,prefix)
    else:raise ValueError('semantic diagram domain must be electrical or mechanical')
    for note in data.get('notes',[]):canvas.label(note['text'],*point(note['at']),size=note.get('size',22))
    return ''.join(canvas.parts)
