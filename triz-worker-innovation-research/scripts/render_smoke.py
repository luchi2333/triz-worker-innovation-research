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
from research_contract import digest


def inspect_pdf(pdf,output,docx=None):
    import fitz
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    errors=[];pages=[]
    with fitz.open(pdf) as document:
        if not 1<=len(document)<=12:errors.append('example page count outside 1..12')
        for index,page in enumerate(document):
            text=page.get_text();image=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
            path=output/f'page-{index+1}.png';image.save(path)
            if '\ufffd' in text:errors.append(f'page {index+1}: replacement glyph detected')
            # A page may legitimately be image-only; test actual nonwhite pixels.
            samples=image.samples
            ink=sum(1 for i in range(0,len(samples),image.n) if min(samples[i:i+3])<240)
            if ink/(image.width*image.height)<.0008:errors.append(f'page {index+1}: likely blank')
            for block in page.get_text('dict')['blocks']:
                rect=fitz.Rect(block['bbox'])
                if not (page.rect+(-2,-2,2,2)).contains(rect):errors.append(f'page {index+1}: content outside page bounds')
            pages.append({'page':index+1,'path':path.name,'sha256':digest(path),'text_characters':len(text),
                          'fonts':[f[3] for f in page.get_fonts()]})
    result={'status':'FAIL' if errors else 'RENDER_SMOKE_PASS','pdf_sha256':digest(pdf),'pages':pages,
            'errors':errors,'visual_review':'pending','scope':'page count, render, blank pixels, replacement glyphs, block bounds'}
    if docx:result['docx_sha256']=digest(docx)
    (output/'render-receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def render(docx,output,executable=None):
    docx=Path(docx).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    executable=executable or shutil.which('libreoffice') or shutil.which('soffice')
    if not executable:raise ValueError('LibreOffice is required for render smoke; install it or use an externally rendered --pdf')
    pdf=output/(docx.stem+'.pdf')
    if pdf.exists():raise ValueError('render output PDF already exists; use a fresh output directory')
    with tempfile.TemporaryDirectory(prefix='triz-lo-') as profile:
        run=subprocess.run([str(executable),'-env:UserInstallation='+Path(profile).as_uri(),'--headless','--convert-to','pdf',
                            '--outdir',str(output),str(docx)],capture_output=True,text=True,timeout=120)
        if run.returncode or not pdf.is_file():raise ValueError('DOCX render failed: '+run.stderr[-1000:])
    return inspect_pdf(pdf,output,docx)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--docx',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--libreoffice');parser.add_argument('--pdf',type=Path)
    args=parser.parse_args()
    result=inspect_pdf(args.pdf,args.output,args.docx) if args.pdf else render(args.docx,args.output,args.libreoffice)
    print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(0 if not result['errors'] else 2)
