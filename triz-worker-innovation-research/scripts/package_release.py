"""Build deterministic release ZIP and SHA-256 manifest; does not publish anything."""
import sys
sys.dont_write_bytecode=True
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile
from update_skill import NAME, inventory, metadata, validate


def package(source, output, commit):
    source=Path(source).resolve();output=Path(output).resolve()
    if source==output or source in output.parents:raise ValueError('release output must be outside skill')
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('release requires full commit SHA')
    files=inventory(source)
    version=metadata((source/'SKILL.md').read_text(encoding='utf-8-sig'))
    output.mkdir(parents=True,exist_ok=True)
    archive=output/f'{NAME}-v{version}.zip'
    if archive.exists() or (output/'release-manifest.json').exists():raise ValueError('release artifacts already exist; use a fresh output directory')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in files:
            info=zipfile.ZipInfo('release/'+NAME+'/'+name,date_time=(2000,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,(source/name).read_bytes())
    result=dict(skill=NAME,version=version,commit=commit,archive=archive.name,
                archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),files=files)
    (output/'release-manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--commit',required=True)
    args=parser.parse_args()
    source=args.source.resolve()
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(source),'status','--porcelain','--','.'],text=True).strip()
    if head!=args.commit or dirty:raise ValueError('Release packaging requires a clean skill checkout at the specified commit')
    validate(args.source)
    print(json.dumps(package(args.source,args.output,args.commit),ensure_ascii=False,indent=2))
