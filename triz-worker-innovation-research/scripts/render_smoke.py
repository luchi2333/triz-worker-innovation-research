"""Optional DOCX -> LibreOffice PDF -> page PNG smoke check (requires PyMuPDF).

This checks rendering/blank pages/bounds, not semantic or complete visual quality.
"""
import sys
sys.dont_write_bytecode=True
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unicodedata
from xml.etree import ElementTree as ET
import zipfile
from research_contract import digest


def inspect_pdf(pdf,output,docx=None,max_pages=12):
    import fitz
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    errors=[];pages=[];pdf_text=[]
    with fitz.open(pdf) as document:
        if max_pages < 0:raise ValueError('max_pages must be nonnegative; zero means no upper limit')
        if len(document) < 1 or (max_pages and len(document) > max_pages):errors.append(f'page count outside 1..{max_pages or "unlimited"}')
        for index,page in enumerate(document):
            text=page.get_text();image=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
            pdf_text.append(text)
            path=output/f'page-{index+1}.png';image.save(path)
            if '\ufffd' in text:errors.append(f'page {index+1}: replacement glyph detected')
            # A page may legitimately be image-only; test actual nonwhite pixels.
            samples=image.samples
            ink=sum(1 for i in range(0,len(samples),image.n) if min(samples[i:i+3])<240)
            if ink/(image.width*image.height)<.0008:errors.append(f'page {index+1}: likely blank')
            for block in page.get_text('dict')['blocks']:
                # LibreOffice/PDF converters may split an embedded SVG into
                # hundreds of tiny image blocks.  Some boundary fragments
                # have zero width or a one-pixel negative edge even though the
                # enclosing drawing is fully on the page.  Bounds are a text
                # layout check here; image visibility is covered by the ink
                # ratio and the required visual review.
                if block.get('type') != 0:
                    continue
                rect=fitz.Rect(block['bbox'])
                if not (page.rect+(-2,-2,2,2)).contains(rect):errors.append(f'page {index+1}: content outside page bounds')
            pages.append({'page':index+1,'path':path.name,'sha256':digest(path),'text_characters':len(text),
                          'fonts':[f[3] for f in page.get_fonts()]})
    coverage = {'status':'NOT_CHECKED'}
    if docx:
        def normalize(value):
            return ''.join(c for c in unicodedata.normalize('NFKC',value) if not c.isspace() and unicodedata.category(c) != 'Cf')
        rendered = normalize(''.join(pdf_text));missing=[];checked=0
        with zipfile.ZipFile(docx) as package:
            document=ET.fromstring(package.read('word/document.xml'))
        ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        for paragraph in document.iter(ns+'p'):
            value=''.join(t.text or '' for t in paragraph.iter(ns+'t'))
            if not value.strip():continue
            checked+=1
            if normalize(value) not in rendered:missing.append(value[:100])
        coverage={'status':'FAIL' if missing else 'PASS','paragraphs_checked':checked,'missing_excerpts':missing}
        if missing:errors.append(f'{len(missing)} DOCX paragraphs absent or incomplete in rendered PDF text')
    result={'status':'FAIL' if errors else 'RENDER_SMOKE_PASS','pdf_sha256':digest(pdf),'pages':pages,
            'errors':errors,'visual_review':'pending','max_pages':max_pages,'docx_text_coverage':coverage,
            'scope':'page count, render, blank pixels, replacement glyphs, text bounds and DOCX paragraph text coverage; no semantic certification'}
    if docx:result['docx_sha256']=digest(docx)
    (output/'render-receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def render(docx,output,executable=None,max_pages=12):
    docx=Path(docx).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    executable=executable or shutil.which('libreoffice') or shutil.which('soffice')
    if not executable:raise ValueError('LibreOffice is required for render smoke; install it or use an externally rendered --pdf')
    pdf=output/(docx.stem+'.pdf')
    if pdf.exists():raise ValueError('render output PDF already exists; use a fresh output directory')
    with tempfile.TemporaryDirectory(prefix='triz-lo-') as profile:
        run=subprocess.run([str(executable),'-env:UserInstallation='+Path(profile).as_uri(),'--headless','--convert-to','pdf',
                            '--outdir',str(output),str(docx)],capture_output=True,text=True,timeout=120)
        if run.returncode or not pdf.is_file():raise ValueError('DOCX render failed: '+run.stderr[-1000:])
    return inspect_pdf(pdf,output,docx,max_pages)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--docx',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--libreoffice');parser.add_argument('--pdf',type=Path)
    parser.add_argument('--max-pages',type=int,default=12,help='Example limit defaults to 12; use 0 for full reports. Other checks remain enabled.')
    args=parser.parse_args()
    result=inspect_pdf(args.pdf,args.output,args.docx,args.max_pages) if args.pdf else render(args.docx,args.output,args.libreoffice,args.max_pages)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if not result['errors'] else 2)
