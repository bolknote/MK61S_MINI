"""Bind the physical public-pow corpus to changed internal ARM paths, offline."""
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path.cwd();WORK=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests'))
from native_eabi_m0_arm_self_test import Machine
from unicorn import UC_HOOK_CODE
cfg=json.loads((WORK/'benchmark.json').read_text())
m=Machine(Path(cfg['firmware_elf']),True,stack_bytes=16384,instruction_budget=200000000,bootrom=Path(cfg['bootrom']))
names=['pow_root128','pow_sqrt64_raw','pow_integer128_square','pow_integer128_multiply',
       'pow_integer128_base','factor64_multiply','pow_root128_decide','root64_boundary','root64_distance']
names += [n for n in m.elf.symbols if 'factor_inverse' in n or 'root128_side' in n or 'root128_compare' in n]
names=sorted(set(names));counts={n:0 for n in names};examples={};context={}
def enter(uc,address,size,name):
    counts[name]+=1;examples.setdefault(name,dict(context))
for name in names:
    address=m.elf.symbols[name]&~1
    m.uc.hook_add(UC_HOOK_CODE,enter,name,begin=address,end=address)
calls=0
for chunk in cfg['chunks']+cfg.get('verification_canaries',[]):
    if chunk['operation']!='pow':continue
    for a,b,want in struct.iter_unpack('<3Q',Path(chunk['input']).read_bytes()[32:]):
        context.update(chunk=chunk['index'],a=f'{a:016X}',b=f'{b:016X}',expected=f'{want:016X}')
        assert m.call(chunk['own_symbol'],a,b)[0]==want
        calls+=1
record=dict(status='PASS_PUBLIC_POW_HIL_CORPUS_PATH_ATTRIBUTION',cases=calls,paths=counts,examples=examples,
    all_required_paths_observed=all(counts[n] for n in names),
    elf_sha256=cfg['elf_sha256'],producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Exact V138 public pow on frozen HIL inputs, with hooks only to attribute reached changed integer/root/midpoint paths. This is finite offline path coverage, not a new full numerical qualification or physical timing.')
(WORK/'path-coverage.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(dict(cases=calls,paths=counts,all_observed=record['all_required_paths_observed'])),flush=True)
