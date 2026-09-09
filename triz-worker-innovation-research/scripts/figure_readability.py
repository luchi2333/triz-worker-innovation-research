"""Effective SVG label sizes at actual DOCX image extents, not manifest widths."""
import math
import re
from xml.etree import ElementTree as ET


def svg_font_points(path, width_pt, height_pt):
    root=ET.parse(path).getroot()
    view=[float(x) for x in re.split(r'[ ,]+',root.get('viewBox','').strip())]
    if len(view)!=4 or min(view[2:])<=0 or min(width_pt,height_pt)<=0:
        raise ValueError('invalid SVG viewBox or actual DOCX extent')
    ratio=min(width_pt/view[2],height_pt/view[3])
    sizes=[]
    def walk(node, inherited=16, scale=1):
        kind=node.tag.rsplit('}',1)[-1]
        if kind in {'defs','marker','pattern','clipPath','symbol'}:return
        transform=node.get('transform','')
        consumed=''
        for command,args in re.findall(r'(\w+)\(([^)]*)\)',transform):
            values=[float(x) for x in re.split(r'[ ,]+',args.strip())]
            consumed+=command+'('+args+')'
            if command=='scale' and len(values) in {1,2}:scale*=min(abs(v) for v in values)
            elif command in {'translate','rotate'}:pass
            else:raise ValueError('SVG transform needs explicit readability support: '+command)
        if re.sub(r'\s+','',consumed)!=re.sub(r'\s+','',transform):raise ValueError('unparsed SVG transform')
        style=node.get('style','')
        css=re.search(r'(?:^|;)\s*font-size\s*:\s*([^;]+)',style)
        raw=css[1] if css else node.get('font-size')
        size=inherited
        if raw is not None:
            m=re.fullmatch(r'\s*([\d.]+)(px|pt)?\s*',raw)
            if not m:raise ValueError('relative/CSS font size requires resolved SVG font-size')
            size=float(m[1])*(96/72 if m[2]=='pt' else 1)
        if kind in {'text','tspan'} and node.text and node.text.strip():
            effective=size*scale*ratio
            if not math.isfinite(effective):raise ValueError('nonfinite effective font')
            sizes.append(effective)
        for child in node:walk(child,size,scale)
    # Global font-size CSS could override presentation attributes. Require flattening
    # before checking rather than silently trusting the smaller set of attributes.
    for style in root.iter():
        if style.tag.rsplit('}',1)[-1]=='style' and re.search(r'font(?:-size)?\s*:',style.text or ''):
            raise ValueError('flatten stylesheet font sizes into SVG attributes before validation')
    walk(root)
    if not sizes:raise ValueError('SVG has no measurable text')
    return min(sizes)


def check_control_extent(control, svg, errors):
    wp='{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
    extents=list(control.iter(wp+'extent'))
    if not extents:
        errors.append('bound figure missing actual DOCX extent')
        return
    for extent in extents:
        try:
            width=int(extent.get('cx','0'))/12700
            height=int(extent.get('cy','0'))/12700
            effective=svg_font_points(svg,width,height)
            if effective<6:errors.append(f'actual DOCX effective SVG font-size below 6pt: {effective:.2f}pt')
        except (ValueError,TypeError,ET.ParseError) as exc:errors.append('actual DOCX readability: '+str(exc))
