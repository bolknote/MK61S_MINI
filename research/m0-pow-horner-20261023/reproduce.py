"""Reproduce the exact V138 source in a new private directory; never install it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path.cwd().resolve()
archive = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parent-source', type=Path,
                    default=Path('.build/m0-pow-root-prefix-v122-20261023/source'))
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--build', action='store_true')
parser.add_argument('--sdk', type=Path)
parser.add_argument('--toolchain', type=Path)
args = parser.parse_args()
parent, output = args.parent_source.resolve(), args.output.resolve()
try:
    output.relative_to(root)
except ValueError:
    parser.error('--output must be inside the repository')
if output.exists():
    parser.error('--output must be a new directory')
if args.build and (args.sdk is None or args.toolchain is None):
    parser.error('--build requires --sdk and --toolchain')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(tree):
    return {str(p.relative_to(tree)): sha(p) for p in sorted(tree.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


expected = json.loads((archive/'source-files.json').read_text())
assert files(parent) == expected['V122']['files'], 'Parent differs from pinned V122'
output.mkdir(parents=True)
source = output/'source'
shutil.copytree(parent, source, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
patch = archive/'hybrid-from-V122.patch'
command = ['git', 'apply', '--whitespace=nowarn',
           '--directory='+str(source.relative_to(root)), str(patch)]
subprocess.run(command[:2]+['--check']+command[2:], cwd=root, check=True)
subprocess.run(command, cwd=root, check=True)
actual = files(source)
assert actual == expected['V138']['files'], 'Reproduced source differs from pinned V138'
record = dict(status='PASS_SOURCE_REPRODUCTION', source_files=len(actual),
              source_sha256=expected['V138']['source_sha256'],
              patch_sha256=sha(patch), parent_source=str(parent),
              complete_file_hashes_equal=True, hardware_accessed=False,
              production_sources_changed=False)
(output/'source-reproduction.json').write_text(json.dumps(record, indent=2)+'\n')
print('PASS:', len(actual), 'source files match V138 byte for byte.', flush=True)
if args.build:
    subprocess.run([sys.executable, str(source/'tools/build_picocalc.py'),
                    '--sdk', str(args.sdk.resolve()), '--toolchain', str(args.toolchain.resolve()),
                    '--build-path', str(output/'build'), '--output-dir', str(output/'firmware'),
                    '--jobs', '4'], cwd=root, check=True)
