"""Read-only verification of the private candidate, evidence and unchanged V138 pins."""
import ast
import hashlib
import json
from pathlib import Path

root = Path.cwd()
work = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


seal = json.loads((work/'FROZEN.json').read_text())
for name,digest in seal['files'].items():
    p = work/name
    assert p.is_file() and not p.is_symlink() and sha(p)==digest, name
    if p.suffix=='.json':
        json.loads(p.read_text())
    if p.suffix=='.py':
        ast.parse(p.read_text(),filename=str(p))
handoff = json.loads((work/'HANDOFF.json').read_text())
assert handoff['candidate']=='V144' and handoff['build']=='4CA2268A'
checked = set()


def references(value):
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
            p = root/value['path']
            assert p.is_file() and sha(p)==value['sha256'], p
            checked.add((value['path'],value['sha256']))
        for child in value.values():
            references(child)
    elif isinstance(value,list):
        for child in value:
            references(child)


references(handoff)
source = work/'source'
actual = {str(p.relative_to(source)):sha(p) for p in source.rglob('*')
          if p.is_file() and '__pycache__' not in p.parts}
assert len(actual)==646
assert actual==json.loads((work/'preparation.json').read_text())['source_file_hashes']
for name,digest in handoff['approved_V138_package_hashes_unchanged'].items():
    assert sha(root/name)==digest, name
matrix = json.loads((work/'instruction-matrix.json').read_text())
old = json.loads((root/'.build/m0-pow-tiny-stable-v142-20261023/instruction-matrix.json').read_text())
assert matrix['groups']==old['groups'] and matrix['chunks']==old['chunks']
assert handoff['expanded171_groups']==dict(faster=155,equal=2,slower=14,cases=30304)
assert handoff['fresh_directed_MPFR_calls']==161626
assert handoff['fresh_directed_MPFR_pow_calls']==156250
assert handoff['new_allocated_Flash_code_bytes']==1868
assert handoff['exact_old_numerical_linked_bodies']==250
assert handoff['old_numerical_bodies_with_only_verified_equivalent_veneer_BL_relocations']==66
assert handoff['scratch_veneer_target_multiset_identical']
assert handoff['complete_scratch_code_byte_identical'] is False
assert handoff['M4_soft_and_hard_preprocessing_code_and_data_identical']
assert handoff['general_pow_undecided_1024_trap_retained']
assert handoff['general_pow_totality_proved'] is False
assert handoff['goal_complete'] is False and handoff['hardware_accessed'] is False
print('PASS: private V144 seal;',len(checked),'pinned references;646 exact source files; original119 chunk records unchanged; approvedV138 hashes preserved. Goal remains open.')
