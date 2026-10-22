#!/usr/bin/env python3
"""Overlay only memory work onto a frozen Pico source, without other chats' edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-source', type=Path, required=True)
parser.add_argument('--base-manifest', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--placement', choices=('sram', 'flash'), required=True)
args = parser.parse_args()
assert not args.output.exists(), 'Use a new source snapshot'
base = json.loads(args.base_manifest.read_text())
digest = hashlib.sha256()
for source in sorted([args.base_source / 'tools/build_picocalc.py', args.base_source / 'tools/seal_picocalc.py',
                      *(path for folder in ('code', 'ports/picocalc', 'third_party/fatfs', 'third_party/core_math')
                        for path in (args.base_source / folder).rglob('*')
                        if path.is_file() and (path.suffix in ('.c', '.cpp', '.h', '.hpp', '.S', '.inc', '.ld', '.pio')
                                               or path.name == 'CMakeLists.txt'))]):
    digest.update(str(source.relative_to(args.base_source)).encode() + b'\0')
    digest.update(source.read_bytes())
assert digest.hexdigest() == base['source_sha256'], 'Frozen base source differs from its manifest'
shutil.copytree(args.base_source, args.output)
files = ['code/memory_word_ops.h', 'code/system_memory.c', 'sdk/portable/memory.c',
         'ports/picocalc/memory.c', 'ports/picocalc/memory_fill.S']
files += [str(path.relative_to(ROOT)) for pattern in ('memory_*_arm.h', 'memcpy_*.inc', 'memmove_*.inc', 'memcmp_*.inc')
          for path in sorted((ROOT / 'code').glob(pattern))]
for name in files:
    destination = args.output / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, destination)
memory = args.output / 'ports/picocalc/memory.c'
if args.placement == 'flash':
    text = memory.read_text().replace('.time_critical.', '.text.')
    text = text.replace('Speed-selected memcpy/memmove live in SRAM, like the standalone APP implementation.',
                        'Experimental Flash placement of the same measured memory algorithms.')
    memory.write_text(text)
cmake = args.output / 'ports/picocalc/CMakeLists.txt'
text = cmake.read_text()
assert 'pico_mem_ops_mk61' not in text, 'Base already contains memory integration; review the overlay'
root_cmake = (ROOT / 'ports/picocalc/CMakeLists.txt').read_text()
begin = root_cmake.index('pico_add_library(pico_mem_ops_mk61)')
end = root_cmake.index('pico_set_program_name(', begin)
anchor = 'pico_set_double_implementation(mk61s-picocalc-pico-h compiler)\n'
assert text.count(anchor) == 1
cmake.write_text(text.replace(anchor, anchor + root_cmake[begin:end]))
files.append('ports/picocalc/CMakeLists.txt')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
allowed = set(files)
for path in args.base_source.rglob('*'):
    if path.is_file() and str(path.relative_to(args.base_source)) not in allowed:
        assert sha(path) == sha(args.output / path.relative_to(args.base_source)), path
receipt = dict(status='PREPARED_NOT_HARDWARE_ACCEPTED', base_build=base['build_id'],
               base_manifest_sha256=sha(args.base_manifest), base_source_sha256=base['source_sha256'],
               placement=args.placement, overlay_sha256={name: sha(args.output / name) for name in sorted(allowed)},
               other_source_files_unchanged=True)
(args.output.parent / (args.output.name + '-overlay.json')).write_text(json.dumps(receipt, indent=2) + '\n')
print('Prepared', args.placement, 'memory-only source; other platform/math files unchanged')
