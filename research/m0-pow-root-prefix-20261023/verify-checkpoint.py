"""Check archive hashes and keep the candidate and unqualified draft evidence distinct."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

root = Path.cwd()
archive = Path(__file__).resolve().parent
draft = archive.parent/'m0-pow-factor-20261023'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check-local', action='store_true', help='Also verify original private report/artifact references')
args = parser.parse_args()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
load = lambda p: json.loads(p.read_text())

for directory in (archive, draft):
    manifest = load(directory/'checkpoint.json')
    actual = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*'))
              if p.is_file() and p.name != 'checkpoint.json' and '__pycache__' not in p.parts}
    assert actual == manifest['files'], directory
    for name in actual:
        path = directory/name
        if path.suffix == '.json':
            load(path)
        elif path.suffix == '.py':
            ast.parse(path.read_text(), filename=str(path))

evidence = load(archive/'evidence.json')
handoff = evidence['handoff']
reports = evidence['reports']
assert handoff['build'] == 'A62D1F7C'
assert handoff['instruction_groups'] == dict(faster=114, equal=2, slower=1)
bridge = reports['V122_equivalence']['report']
assert bridge['elf_sha256'] == handoff['elf']['sha256']
assert len(bridge['identical_numerical_objects_and_relocations']) == 5
assert bridge['surviving_numeric_functions_checked'] == 313
for name in ('V121_all12', 'V121_selected_pow', 'V121_endpoints'):
    assert reports[name]['report']['elf_sha256'] == bridge['parent_elf_sha256']
assert sum(v['cases'] for v in reports['V121_all12']['report']['operations'].values()) == 494206
assert reports['V121_selected_pow']['report']['cases'] == 75229
matrix = reports['V122_matrix']['report']
assert matrix['owned_elf_sha256'] == handoff['elf']['sha256'] and matrix['cases'] == 23352
assert reports['V122_runtime']['report']['status'].startswith('PASS')
for row in reports['V122_cache']['report']['groups']:
    assert row['elf_sha256'] == handoff['elf']['sha256']

prototype = load(draft/'evidence.json')
assert prototype['status'] == 'EXPERIMENTAL_FACTOR_COMPILE_LINK_ONLY'
assert not prototype['correctness_qualified'] and not prototype['performance_measured']
assert prototype['parent_elf_sha256'] == handoff['elf']['sha256']
entry = (draft/'entry.cpp.inc').read_text()
marker = '  PowInteger128 power={((xb&D::Fraction)|D::Hidden)<<11,0,int(xb>>52)-1023,0};'
assert entry.count(marker) == 1
entry = entry.replace(marker, '  if(denominator!=1) return factor_pow(xb,numerator,denominator,inverse);\n'+marker)
assembled = (draft/'before.cpp.inc').read_text()+(draft/'factor.cpp.inc').read_text()+entry
assert assembled == (draft/'kernels.cpp').read_text()
for row in prototype['original_build_report']['report']['variants']:
    assert row['cpp_sha256'] == sha(draft/'kernels.cpp')

checked = set()


def references(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            path = root/value['path']
            assert path.is_file(), path
            assert sha(path) == value['sha256'], path
            checked.add((value['path'], value['sha256']))
        for child in value.values():
            references(child)
    elif isinstance(value, list):
        for child in value:
            references(child)


if args.check_local:
    references(evidence)
    references(prototype)
print('PASS: checkpoint hashes, report/ELF bindings, 313-function bridge and link-only draft scope;',
      len(checked), 'original local references checked.')
