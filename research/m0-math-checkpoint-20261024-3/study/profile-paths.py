"""Attribute actual DIRTY-path costs before integrating the new polynomial."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';D=ROOT/'.build/m0-atan-residual-geometry-20261024'
sys.path.insert(0,str(ROOT/'.build/m0-float-fma-qualification-20261023/support'))
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR
q=json.loads((D/'qualification.json').read_text());e=ElfImage(D/'candidate.elf')
assert hashlib.sha256((D/'candidate.elf').read_bytes()).hexdigest()==q['candidate_ELF_sha256']
m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
e.load(m.uc);m.elf.symbols['candidate_atan']=e.symbols['mk61_m0_atan']
names=('atan_fast','atan_fast_tail_repair','atan_refine')
addresses={e.symbols[n]&~1:n for n in names}
addresses[m.elf.symbols['mk61_m0_cr_atan']&~1]='CORE'
jobs={r['x'] for r in q['remaining_slower_correct_Qfplib']}
jobs.update(('3FE5D1004FC925B6','3FECB99548F4FA32'))
original={r['x']:r for r in q['rows'] if r['SIO']=='DIRTY'}
count=0;trace=[];repair_return=None
def hook(uc,address,size,data):
 global count,repair_return
 count+=1
 if address in addresses:
  trace.append(dict(function=addresses[address],instruction=count))
  if addresses[address]=='atan_fast_tail_repair':repair_return=uc.reg_read(UC_ARM_REG_LR)&~1
 if address==repair_return:
  trace.append(dict(function='repair_return',instruction=count));repair_return=None
hnd=m.uc.hook_add(UC_HOOK_CODE,hook);rows=[]
try:
 for raw in sorted(jobs):
  count=0;trace=[];repair_return=None;state=struct.pack('<7I',17,3,17,3,5,2,3)
  m.uc.mem_write(0xd0000060,state);got=m.call('candidate_atan',int(raw,16))[0]
  r=original[raw];assert count==r['instructions']['candidate'] and got==int(r['outputs']['candidate'],16)
  assert bytes(m.uc.mem_read(0xd0000060,28))==state
  refine=next((s['instruction'] for s in trace if s['function']=='atan_refine'),None)
  enter=next((s['instruction'] for s in trace if s['function']=='atan_fast_tail_repair'),None)
  leave=next((s['instruction'] for s in trace if s['function']=='repair_return'),None)
  rows.append(dict(x=raw,total=count,Qfplib=r['instructions']['Qfplib'],first_fallback_instruction=refine,
                   repair_instructions=leave-enter if enter is not None else None,trace=trace,
                   budget_before_Qfplib=(r['instructions']['Qfplib']-refine) if refine is not None else r['instructions']['Qfplib']-count))
finally:m.uc.hook_del(hnd)
report=dict(status='ATTRIBUTED_ACTUAL_ARM_DIRTY_PATH_COSTS_NOT_NEW_RUNTIME',cases=len(rows),rows=rows,
            full_instruction_counts_reproduced=True,candidate_ELF_sha256=q['candidate_ELF_sha256'],hardware_accessed=False,goal_complete=False)
(W/'path-costs.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps([{k:v for k,v in r.items() if k!='trace'} for r in rows],indent=2))
