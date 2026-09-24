"""Check report evidence coverage and monochrome style, not engineering truth.

Design facts live in research-record.json; review receipts bind to the final DOCX.
Review answers must be read by a reviewer. Presence checks cannot judge physics.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
SECTIONS = ('input_output', 'mechanism', 'implementation', 'worked_example', 'validation', 'innovation_attribution')


def mono(color):
    value = color.strip().lower()
    if value in {'none', 'transparent', 'currentcolor', 'auto', 'black', 'white', 'gray', 'grey'}:
        return True
    if value.startswith('#'):
        value = value[1:]
    if re.fullmatch('[0-9a-f]{3}', value):
        value = ''.join(c * 2 for c in value)
    if re.fullmatch('[0-9a-f]{6}', value):
        return value[:2] == value[2:4] == value[4:]
    match = re.fullmatch(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)', value)
    return bool(match and len(set(match.groups())) == 1)


def svg_style(path):
    errors = []
    root = ET.parse(path).getroot()
    colors = []
    for node in root.iter():
        if node.tag.rsplit('}', 1)[-1] in {'linearGradient', 'radialGradient', 'filter'}:
            errors.append('decorative gradients/filters forbidden, including monochrome')
        for name in ('stroke', 'fill', 'color', 'stop-color'):
            if name in node.attrib:
                colors.append(node.attrib[name])
        css = node.attrib.get('style', '')
        if node.tag.rsplit('}', 1)[-1] == 'style':
            css += node.text or ''
        colors.extend(re.findall(r'(?:^|[;{\s])(?:fill|stroke|color|stop-color)\s*:\s*([^;}]+)', css))
        if node.tag.rsplit('}', 1)[-1] == 'image':
            errors.append('raster-in-SVG requires separate visual style review')
    for color in colors:
        if color.startswith('url('):
            continue  # Gradient/pattern children are checked above.
        if not mono(color):
            errors.append('non-monochrome or unsupported paint: ' + color)
    return sorted(set(errors))


def docx_style(path):
    errors = []
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
        styles = ET.fromstring(archive.read('word/styles.xml')) if 'word/styles.xml' in archive.namelist() else ET.Element('styles')
        style_map = {s.get(W + 'styleId'): s for s in styles.findall(W + 'style')}
        default_styles = {s.get(W + 'styleId') for s in style_map.values() if s.get(W + 'default') == '1'}
        defaults = styles.find(W + 'docDefaults')
        for index, table in enumerate(root.iter(W + 'tbl'), 1):
            prefix = f'table {index}: '
            used = set(default_styles) | {'Normal'}
            used.update(n.get(W + 'val') for n in table.iter() if n.tag in {W + 'pStyle', W + 'rStyle', W + 'tblStyle'})
            resolved, pending = [], list(used)
            visited = set()
            while pending:
                sid = pending.pop()
                if sid in visited:
                    continue
                visited.add(sid)
                item = style_map.get(sid)
                if item is not None:
                    resolved.append(item)
                    parent = item.find(W + 'basedOn')
                    if parent is not None:
                        pending.append(parent.get(W + 'val'))
            if defaults is not None:
                resolved.append(defaults)
            for item in resolved:
                for color in item.iter(W + 'color'):
                    if color.get(W + 'themeColor') or not mono(color.get(W + 'val', 'auto')):
                        errors.append(prefix + 'colored/unsupported inherited text style')
                for shade in item.iter(W + 'shd'):
                    if shade.get(W + 'themeFill') or shade.get(W + 'fill', 'FFFFFF').upper() not in {'FFFFFF', 'AUTO'}:
                        errors.append(prefix + 'colored inherited table/paragraph background')
            borders = table.find(W + 'tblPr/' + W + 'tblBorders')
            if borders is None:
                errors.append(prefix + 'explicit three-line borders missing')
                continue
            for edge in ('top', 'bottom'):
                line = borders.find(W + edge)
                if line is None or line.get(W + 'val') != 'single' or line.get(W + 'color') != '000000':
                    errors.append(prefix + edge + ' must be solid black')
            for edge in ('left', 'right', 'insideV', 'insideH'):
                line = borders.find(W + edge)
                if line is not None and line.get(W + 'val') not in {'nil', 'none'}:
                    errors.append(prefix + 'grid/side border forbidden: ' + edge)
            rows = table.findall(W + 'tr')
            for row_index, row in enumerate(rows):
                for cell_index, cell in enumerate(row.findall(W + 'tc')):
                    content = ''.join(n.text or '' for n in cell.iter(W + 't')).strip()
                    merge = cell.find(W + 'tcPr/' + W + 'vMerge')
                    continuation = merge is not None and merge.get(W + 'val') in {None, 'continue'}
                    if not content and not continuation and cell.find('.//' + W + 'drawing') is None:
                        errors.append(prefix + f'blank cell at row {row_index + 1}, column {cell_index + 1}; data missing or field mapping failed')
            if rows:
                for cell in rows[0].findall(W + 'tc'):
                    line = cell.find(W + 'tcPr/' + W + 'tcBorders/' + W + 'bottom')
                    if line is None or line.get(W + 'val') != 'single' or line.get(W + 'color') != '000000':
                        errors.append(prefix + 'header separation must be solid black')
            for row_index, row in enumerate(rows):
                for cell in row.findall(W + 'tc'):
                    for line in cell.findall(W + 'tcPr/' + W + 'tcBorders/*'):
                        allowed = row_index == 0 and line.tag == W + 'bottom'
                        if not allowed and line.get(W + 'val') not in {'nil', 'none'}:
                            errors.append(prefix + 'cell grid override forbidden')
            for shade in table.iter(W + 'shd'):
                if shade.get(W + 'fill', 'FFFFFF').upper() not in {'FFFFFF', 'AUTO'}:
                    errors.append(prefix + 'table background must be white')
            for color in table.iter(W + 'color'):
                if color.get(W + 'themeColor') or not mono(color.get(W + 'val', 'auto')):
                    errors.append(prefix + 'colored table text forbidden')
        return sorted(set(errors))


def audit_quality(root, manifest):
    root = Path(root).resolve()
    technical, style = [], []
    def resolve(value):
        if not isinstance(value, str) or not value:
            raise ValueError('missing artifact path')
        path = (root / value).resolve()
        if not path.is_relative_to(root):
            raise ValueError('artifact outside project root')
        return path
    docs = {}
    for artifact in manifest.get('artifacts', []):
        if not isinstance(artifact, dict) or not str(artifact.get('path', '')).lower().endswith('.docx'):
            continue
        try:
            path = resolve(artifact['path'])
            style.extend(f'{path.name}: {error}' for error in docx_style(path))
            with zipfile.ZipFile(path) as archive:
                xml = ET.fromstring(archive.read('word/document.xml'))
                def prose(node):
                    if node.tag == W + 'tbl':
                        return  # Table labels/cells alone cannot prove a design explanation.
                    if node.tag == W + 'p':
                        ps = node.find(W + 'pPr/' + W + 'pStyle')
                        name = ps.get(W + 'val', '').lower() if ps is not None else ''
                        if not name.startswith(('heading', 'title', 'subtitle', 'caption')):
                            yield ''.join(n.text or '' for n in node.iter(W + 't'))
                    else:
                        for child in node:
                            yield from prose(child)
                paragraphs = list(prose(xml))
            if artifact.get('role') == 'main-report':
                docs[artifact['path']] = (hashlib.sha256(path.read_bytes()).hexdigest(), {re.sub(r'\s+', '', p) for p in paragraphs})
        except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
            style.append('cannot inspect DOCX: ' + str(exc))
    figures = {f.get('id'): f for f in manifest.get('figures', []) if isinstance(f, dict)}
    for fid, figure in figures.items():
        try:
            style.extend(f'{fid}: {error}' for error in svg_style(resolve(figure.get('source_svg'))))
        except (OSError, ValueError, ET.ParseError) as exc:
            style.append(f'{fid}: cannot inspect SVG: {exc}')
    try:
        record = json.loads(resolve(manifest.get('research_record', {}).get('path')).read_text(encoding='utf-8'))
        if not isinstance(record, dict) or not isinstance(record.get('routes', []), list):
            raise ValueError('research record must be an object with a routes list')
        if not isinstance(record.get('models_and_tests', {}), dict):
            raise ValueError('models_and_tests must be an object')
        receipt_path = manifest.get('report_quality_review', 'report-quality-review.json')
        receipt = json.loads(resolve(receipt_path).read_text(encoding='utf-8')) if resolve(receipt_path).exists() else {}
        if not isinstance(receipt, dict):
            raise ValueError('report quality receipt must be an object')
        dossiers = receipt.get('technical_dossiers', [])
        if not isinstance(dossiers, list):
            raise ValueError('technical_dossiers must be a list')
        by_route = {}
        for dossier in dossiers:
            if not isinstance(dossier, dict) or not dossier.get('route_id'):
                raise ValueError('invalid technical dossier')
            rid = dossier['route_id']
            if rid in by_route:
                technical.append(f'{rid}: duplicate technical dossier')
            by_route[rid] = dossier
        required = {r['id'] for r in record.get('routes', []) if isinstance(r, dict) and r.get('role') not in {'rejected', 'baseline'} and r.get('id')}
        protocol_items = record.get('models_and_tests', {}).get('protocols', [])
        if not isinstance(protocol_items, list):
            raise ValueError('protocols must be a list')
        protocols = {p.get('id'): p for p in protocol_items if isinstance(p, dict)}
        if not required:
            technical.append('no active technical route to review')
        def anchor(value, label):
            if not isinstance(value, dict):
                technical.append(label + ': missing report evidence anchor')
                return
            doc = docs.get(value.get('artifact_path'))
            quote = re.sub(r'\s+', '', str(value.get('quote', '')))
            if not doc or value.get('artifact_sha256') != doc[0]:
                technical.append(label + ': evidence must bind to current main-report DOCX hash')
            if not doc or not quote or quote not in doc[1] or not value.get('location'):
                technical.append(label + ': full-paragraph evidence quote/location not found in main report')
        for rid in sorted(required):
            matching_protocols = [p for p in protocols.values() if rid in p.get('route_ids', [])]
            if not matching_protocols:
                technical.append(f'{rid}: no route-specific validation protocol in research record')
            dossier = by_route.get(rid, {})
            if not dossier:
                technical.append(f'{rid}: missing technical dossier (scheme detail not demonstrated)')
                continue
            for section in SECTIONS:
                anchor(dossier.get(section), rid + '.' + section)
            if dossier.get('domain') not in {'mechanical', 'electrical', 'measurement', 'software', 'control', 'thermal', 'fluid', 'process', 'work'}:
                technical.append(f'{rid}: technical domain missing or invalid')
            protocol = protocols.get(dossier.get('protocol_id'), {})
            if protocol not in matching_protocols or not all(protocol.get(k) for k in ('scope', 'sampling_plan', 'metrics', 'stop_rule')):
                technical.append(f'{rid}: referenced validation protocol incomplete or belongs to another route')
            diagram = dossier.get('diagram', {})
            if not isinstance(diagram, dict):
                diagram = {}
            figure = figures.get(diagram.get('figure_id'))
            if not figure or not diagram.get('why_this_explains_mechanism'):
                technical.append(f'{rid}: mechanism diagram and correspondence explanation missing')
            design_kind = dossier.get('design_kind', 'development')
            if design_kind not in {'development', 'procurement'}:
                technical.append(f'{rid}: design_kind must be development or procurement')
            if dossier.get('domain') in {'electrical', 'measurement'} and design_kind != 'procurement' and diagram.get('kind') != 'equivalent-circuit':
                technical.append(f'{rid}: electrical/measurement design requires equivalent-circuit evidence')
            if design_kind == 'procurement' and diagram.get('kind') not in {'product-interface', 'equivalent-circuit'}:
                technical.append(f'{rid}: procurement route requires product interface/adaptation evidence')
            if diagram.get('kind') not in {'equivalent-circuit', 'section-force-motion', 'algorithm-state', 'process-control', 'product-interface', 'balance-network'}:
                technical.append(f'{rid}: diagram kind must describe mechanism, not generic architecture')
            anchor(diagram.get('report_evidence'), rid + '.diagram')
            review = dossier.get('reader_review', {})
            if not isinstance(review, dict):
                review = {}
            if review.get('status') != 'reviewed' or not review.get('reviewer') or review.get('mode') not in {'independent-agent', 'human-reader', 'serial-reader'}:
                technical.append(f'{rid}: explicit reader review missing (never auto-fill pass)')
            for question in ('trace_example', 'distinguish_failure', 'reproduce_test'):
                answer = review.get(question, {})
                if not isinstance(answer, dict) or not answer.get('answer'):
                    technical.append(f'{rid}: reader must answer {question}')
                else:
                    anchor(answer.get('evidence'), rid + '.reader.' + question)
            if review.get('open_issues') != []:
                technical.append(f'{rid}: unresolved reader issues')
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        technical.append('cannot inspect technical dossiers: ' + str(exc))
    return {'technical_status': 'EVIDENCE_RECORDED' if not technical else 'NEEDS_REVISION',
            'style_status': 'PASS' if not style else 'FAIL',
            'technical_errors': technical, 'style_errors': style, 'errors': technical + style,
            'scope': 'Evidence coverage and recorded review only; no proof of engineering validity or reviewer independence.'}
