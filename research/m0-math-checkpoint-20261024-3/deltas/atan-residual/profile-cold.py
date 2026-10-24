"""Measure every CORE-MATH route found by the full functional corpus."""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import equal
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
q=json.loads((W/'qualification.json').read_text());assert q['source_sha256']==sha(W/'native_eabi_m0_atan_fast.inc')
assert q['candidate_ELF_sha256']==sha(W/'candidate.elf')
rom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ref=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
machines={'resident':Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom),'Qfplib':Machine(ref,True)}
for label,filename in [('parent','control.elf'),('candidate','candidate.elf')]:
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=rom);e=ElfImage(W/filename);e.load(m.uc)
 m.elf.symbols[label+'_atan']=e.symbols['mk61_m0_atan'];machines[label]=m
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
o=Oracle();rows=[]
for original in q['rows']:
 if not original['candidate_CORE_entries']:continue
 raw=int(original['x'],16);expected=o.reference('atan',raw);outputs={};counts={};correct={}
 for label,m in machines.items():
  state=states[original['SIO']];m.uc.mem_write(0xd0000060,state)
  name='mk61_m0_atan' if label=='resident' else 'audit_atan' if label=='Qfplib' else label+'_atan'
  got,_,n=m.call(name,raw,count=True);outputs[label]=f'{got:016X}';counts[label]=n;correct[label]=equal(got,expected,64)
  if label!='Qfplib':
   assert correct[label]
   if label in original['outputs']:assert outputs[label]==original['outputs'][label]
  after=bytes(m.uc.mem_read(0xd0000060,28))
  if original['SIO']=='DIRTY':assert after==state
  else:assert not struct.unpack('<7I',after)[6]&2
 rows.append(dict(x=original['x'],SIO=original['SIO'],originally_profiled=original['profiled'],outputs=outputs,instructions=counts,correct=correct))
losses=[r for r in rows if r['correct']['Qfplib'] and r['instructions']['candidate']>r['instructions']['Qfplib']]
report=dict(status='MEASURED_ALL_OBSERVED_CORE_ROUTES_NOT_SPEED_COMPLETE',cases=len(rows),ARM_calls=4*len(rows),
            unique_inputs=len({r['x'] for r in rows}),remaining_correct_Qfplib_slower_rows=len(losses),remaining_correct_Qfplib_slower_inputs=len({r['x'] for r in losses}),
            candidate_wrong=0,rows=rows,full_qualification_sha256=sha(W/'qualification.json'),source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),candidate_ELF_sha256=sha(W/'candidate.elf'),
            instructions_are_not_cycles=True,hardware_accessed=False,goal_complete=False)
(W/'cold-profile.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
print(json.dumps([dict(x=r['x'],SIO=r['SIO'],instructions=r['instructions']) for r in losses],indent=2))
