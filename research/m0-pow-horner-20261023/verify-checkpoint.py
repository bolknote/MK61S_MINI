"""Verify archive integrity and finite V138 evidence, optionally its private originals."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

root = Path.cwd()
archive = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check-local', action='store_true')
args = parser.parse_args()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


manifest = load(archive/'checkpoint.json')
actual = {str(p.relative_to(archive)): sha(p) for p in sorted(archive.rglob('*'))
          if p.is_file() and p.name != 'checkpoint.json' and '__pycache__' not in p.parts}
assert actual == manifest['files'], 'Archive file hashes differ'
for name in actual:
    path = archive/name
    if path.suffix == '.json':
        load(path)
    elif path.suffix == '.py':
        ast.parse(path.read_text(), filename=str(path))

h = load(archive/'HANDOFF.json')
provenance = load(archive/'provenance.json')
reports = {name: load(archive/'reports'/f'{name}.json') for name in h['reports']}
assert h['candidate'] == 'V138' and h['build'] == '83CF4AC4'
assert h['elf']['sha256'] == 'f4010ce9153d8b9776b236751fcfe67da5e528c2bff5725f87478fec74a42895'
assert h['instruction_groups'] == dict(faster=115, equal=2, slower=0)
for name, report in reports.items():
    assert report['status'].startswith('PASS'), name
    if 'elf_sha256' in report:
        assert report['elf_sha256'] == h['elf']['sha256'], name
    assert sha(archive/'reports'/f'{name}.json') == h['reports'][name]['sha256'], name
for name, ref in provenance['archived_originals'].items():
    assert sha(archive/name) == ref['sha256'], name
assert sum(row['cases'] for row in reports['all12']['operations'].values()) == 494206
assert all(row['wrong_rounding'] == 0 for row in reports['all12']['operations'].values())
affected = reports['affected_pow']
assert affected['cases'] == 75229 and affected['wrong_rounding'] == 0 and affected['complete_corpus']
matrix = reports['matrix']
assert matrix['owned_elf_sha256'] == h['elf']['sha256'] and matrix['cases'] == 23352
assert matrix['owned_wrong_rounding'] == 0 and len(matrix['chunks']) == 119
assert [matrix['instruction_groups_'+k] for k in ('faster', 'equal', 'slower')] == [115, 2, 0]
assert reports['extra_endpoints']['direct_power_cases'] == 12397
assert reports['retained128_states']['counts'] == dict(squares=6000, products=6000, base_products=6000, aliases=353)
validation = reports['source_kernel_resources']
assert len(validation['unchanged_numerical_object_allocations_and_relocations']) == 4
assert validation['unchanged_non_pow_linked_functions'] == 206
assert validation['new_tables'] == 0 and validation['additional_global_RAM'] == 0
assert h['physical_timing_available'] is False and h['goal_complete'] is False
terminal = load(archive/'reports/qualification-terminal.json')
assert len(terminal) == 11 and all(row['exit_code'] == 0 for row in terminal)
assert len(reports['cache']['groups']) == 19
assert all(row['elf_sha256'] == h['elf']['sha256'] for row in reports['cache']['groups'])
expected = load(archive/'source-files.json')
scope = reports['source_scope']
assert len(expected['V138']['files']) == len(expected['V122']['files']) == 646
for name in scope['bases']['V122']['modified']:
    assert sha(archive/'source'/name) == expected['V138']['files'][name]
assert len(scope['bases']['V122']['modified']) == 5 and not scope['bases']['V122']['added']
assert sha(archive/'kernels.cpp') == reports['certificate']['reference_cpp_sha256']
assert sha(archive/'kernels-gnu.S') == reports['GNU_reference']['assembly_sha256']

checked = set()


def references(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            path = root/value['path']
            assert path.is_file() and sha(path) == value['sha256'], path
            checked.add((value['path'], value['sha256']))
        for child in value.values():
            references(child)
    elif isinstance(value, list):
        for child in value:
            references(child)


if args.check_local:
    references(h)
    references(provenance)
print('PASS: V138 archive, exact report bindings and finite 115/2/0 gate;',
      len(checked), 'original local references checked.')
