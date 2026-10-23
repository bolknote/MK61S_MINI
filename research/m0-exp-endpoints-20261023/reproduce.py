"""Reproduce exact V145/V144 source in a new private tree; never install it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root=Path.cwd().resolve();archive=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--parent-source',type=Path,default=Path('.build/m0-pow-horner-final-v138-20261023/source'))
p.add_argument('--candidate',choices=('V145','V144'),default='V145')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--build',action='store_true')
p.add_argument('--sdk',type=Path)
p.add_argument('--toolchain',type=Path)
a=p.parse_args()
parent=a.parent_source.resolve();output=a.output.resolve()
try:
    output.relative_to(root)
except ValueError:
    p.error('--output must be inside the repository')
if output.exists():
    p.error('--output must be a new directory')
if a.build and (a.sdk is None or a.toolchain is None):
    p.error('--build requires --sdk and --toolchain')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(tree):
    return {str(f.relative_to(tree)):sha(f) for f in sorted(tree.rglob('*'))
            if f.is_file() and '__pycache__' not in f.parts}


expected=json.loads((archive/'source-files.json').read_text())
assert files(parent)==expected['V138']['files'],'Parent differs from pinned V138'
scope=json.loads((archive/'source-scope.json').read_text())['bases'][a.candidate]
patch=archive/scope['patch']
assert sha(patch)==scope['patch_sha256']
output.mkdir(parents=True)
source=output/'source'
shutil.copytree(parent,source,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
command=['git','apply','--whitespace=nowarn','--directory='+str(source.relative_to(root)),str(patch)]
subprocess.run(command[:2]+['--check']+command[2:],cwd=root,check=True)
subprocess.run(command,cwd=root,check=True)
assert files(source)==expected[a.candidate]['files'],'Reproduced source differs from the tested candidate'
record=dict(status='PASS_SOURCE_REPRODUCTION',candidate=a.candidate,source_files=646,
    source_sha256=expected[a.candidate]['source_sha256'],patch_sha256=sha(patch),
    complete_file_hashes_equal=True,hardware_accessed=False,canonical_sources_changed=False)
(output/'source-reproduction.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',a.candidate,'646 source files match the tested candidate byte for byte.',flush=True)
if a.build:
    subprocess.run([sys.executable,str(source/'tools/build_picocalc.py'),
        '--sdk',str(a.sdk.resolve()),'--toolchain',str(a.toolchain.resolve()),
        '--build-path',str(output/'build'),'--output-dir',str(output/'firmware'),'--jobs','4'],cwd=root,check=True)
