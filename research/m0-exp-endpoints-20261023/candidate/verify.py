"""Read-only integrity and coverage checks for private V145 evidence."""
import ast
import hashlib
import json
from pathlib import Path

root=Path.cwd();work=Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


seal=json.loads((work/'FROZEN.json').read_text())
for name,digest in seal['files'].items():
    p=work/name
    assert p.is_file() and not p.is_symlink() and sha(p)==digest,name
    if p.suffix=='.json':
        json.loads(p.read_text())
    if p.suffix=='.py':
        ast.parse(p.read_text(),filename=str(p))
d=json.loads((work/'HANDOFF.json').read_text())
assert d['candidate']=='V145' and d['build']=='8498B317'
checked=set()


def references(v):
    if isinstance(v,dict):
        if isinstance(v.get('path'),str) and isinstance(v.get('sha256'),str):
            p=root/v['path'];assert p.is_file() and sha(p)==v['sha256'],p
            checked.add((v['path'],v['sha256']))
        for child in v.values():
            references(child)
    elif isinstance(v,list):
        for child in v:
            references(child)


references(d)
source=work/'source'
actual={str(p.relative_to(source)):sha(p) for p in source.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert len(actual)==646 and actual==json.loads((work/'preparation.json').read_text())['source_file_hashes']
for name,digest in d['approved_V138_package_hashes_unchanged'].items():
    assert sha(root/name)==digest,name
assert d['expanded171_groups']==dict(faster=156,equal=2,slower=13,cases=30304)
assert d['fresh_directed_MPFR_calls']==105478 and d['fresh_directed_MPFR_exp_calls']==99138
assert d['actual_ARM_integer_interval_cases']==176440
assert d['old_other_exact_numerical_bodies']==248
assert d['other_numerical_bodies_with_only_verified_equivalent_old_BL_relocations']==70
assert d['new_allocated_Flash_bytes_vs_V144']==392 and d['new_tables']==d['new_global_RAM']==0
assert d['main_static_RAM_bytes']==198856 and d['scratch_bytes']==4072 and d['image_extent_bytes']==1537400
assert d['M4_soft_and_hard_preprocessing_code_and_data_identical']
assert d['general_pow_undecided_1024_trap_retained']
assert d['goal_complete'] is False and d['hardware_accessed'] is False
print('PASS: private V145 seal;',len(checked),'pinned references;646 exact source files; all171 groups retained; V144 and approvedV138 hashes preserved. Goal remains open.')
