"""Read-only archive/source/evidence bindings; optional historical private checks."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

root=Path.cwd();archive=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--check-local',action='store_true')
a=p.parse_args()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


seal=load(archive/'checkpoint.json')
actual={str(f.relative_to(archive)):sha(f) for f in sorted(archive.rglob('*'))
        if f.is_file() and f.name!='checkpoint.json' and '__pycache__' not in f.parts}
assert actual==seal['files'],'Checkpoint file set or hashes differ'
for name in actual:
    f=archive/name
    if f.suffix=='.json':
        load(f)
    elif f.suffix=='.py':
        ast.parse(f.read_text(),filename=str(f))
provenance=load(archive/'provenance.json')
for name,r in provenance['archived_originals'].items():
    assert sha(archive/name)==r['sha256'],name
reports={};handoffs={}
for label,prefix in (('V145','candidate'),('V144','lineage/V144')):
    base=archive/prefix
    original=load(base/'FROZEN.json')
    for name,digest in original['files'].items():
        if name not in provenance['omitted_compiled_artifacts'][label]:
            assert sha(base/name)==digest,(label,name)
    h=load(base/'HANDOFF.json');handoffs[label]=h
    assert h['candidate']==label and h['goal_complete'] is False
    origin=Path(provenance['archived_originals'][prefix+'/HANDOFF.json']['path']).parent
    reports[label]={}
    for name,r in h['reports'].items():
        f=base/Path(r['path']).relative_to(origin)
        d=load(f);reports[label][name]=d
        assert sha(f)==r['sha256'] and d['status'].startswith('PASS'),(label,name)
        for field in ('elf_sha256','owned_elf_sha256'):
            if field in d:
                assert d[field]==h['elf']['sha256'],(label,name)
v=reports['V145'];h=handoffs['V145']
assert h['build']=='8498B317' and h['elf']['sha256']=='209ac74c551923630300a4def7d017e90f2a69799bd4b800a8627955c16b5cf6'
assert h['expanded171_groups']==dict(faster=156,equal=2,slower=13,cases=30304)
assert len(v['expanded']['groups'])==171 and len(v['expanded']['raw_deficits'])==13
assert h['fresh_directed_MPFR_calls']==105478 and h['fresh_directed_MPFR_exp_calls']==99138
assert v['qualification']['cases']==58302 and v['qualification']['wrong_rounding']==0
assert v['random']['operations']['exp']['cases']==40196
assert v['property']['cases']==176440 and v['property']['accepted']==68075
assert v['matrix']['cases']==23352 and len(v['matrix']['chunks'])==119
assert v['expanded']['unchanged_original_chunk_records']==116
assert v['expanded']['unchanged_independent_group_records']==48
assert v['canary']['cases']==30
terminal=load(archive/'candidate/terminal-observations.json')
assert len(terminal['processes'])==12 and all(t['exit_code']==0 for t in terminal['processes'])
assert h['new_allocated_Flash_bytes_vs_V144']==392 and h['new_tables']==h['new_global_RAM']==0
assert h['M4_soft_and_hard_preprocessing_code_and_data_identical']
assert h['general_pow_undecided_1024_trap_retained'] and h['general_pow_totality_proved'] is False
assert handoffs['V144']['build']=='4CA2268A'
assert reports['V144']['small_qualification']['cases']==39022
assert reports['V144']['affected']['cases']==75229
assert reports['V144']['random']['operations']['pow']['cases']==40395
expected=load(archive/'source-files.json');scope=load(archive/'source-scope.json')['bases']
for label in ('V138','V144','V145'):
    assert len(expected[label]['files'])==646
for label,prefix in (('V145','source'),('V144','lineage/V144/source')):
    assert sha(archive/scope[label]['patch'])==scope[label]['patch_sha256']
    changed=[name for name,digest in expected['V138']['files'].items() if expected[label]['files'][name]!=digest]
    assert changed==scope[label]['modified'] and not scope[label]['added'] and not scope[label]['removed']
    for name in changed:
        assert sha(archive/prefix/name)==expected[label]['files'][name],(label,name)
assert len(scope['V145']['modified'])==4 and len(scope['V144']['modified'])==3
assert expected['V145']['source_sha256']==h['source_sha256']
checked=set()


def references(value):
    if isinstance(value,dict):
        if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
            f=root/value['path'];assert f.is_file() and sha(f)==value['sha256'],f
            checked.add(value['path'])
        for child in value.values():
            references(child)
    elif isinstance(value,list):
        for child in value:
            references(child)


if a.check_local:
    references(provenance)
    for label,hh in handoffs.items():
        references(hh)
    for label,dirname in (('V138','m0-pow-horner-final-v138-20261023'),
                          ('V144','m0-pow-small-y-stable-v144-20261023'),
                          ('V145','m0-exp-endpoints-v145-20261023')):
        source=root/'.build'/dirname/'source'
        values={str(f.relative_to(source)):sha(f) for f in source.rglob('*')
                if f.is_file() and '__pycache__' not in f.parts}
        assert values==expected[label]['files'],label
print('PASS: V145 checkpoint;',len(actual),'archive files;',len(provenance['archived_originals']),
      'exact originals;',len(checked),'local references;171 groups156/2/13. Goal remains open.')
