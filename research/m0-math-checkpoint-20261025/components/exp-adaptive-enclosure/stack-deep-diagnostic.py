"""Like-for-like parent/child stack check on new deep endpoint controls."""
from pathlib import Path
import json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];C=ROOT/'.build/m0-exp-tiny-log-midpoint-20261024';P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP
q=json.loads((W/'qualification.json').read_text());candidates={}
for r in q['remaining']:
 x=int(r['x'],16)
 if r['parent_instructions'] is None:candidates.setdefault(x,r)
key=lambda x:abs(struct.unpack('<d',struct.pack('<Q',x))[0])
jobs={x:candidates[x] for x in sorted(candidates,key=key)[:64]}
machines={};lowest={}
for label,folder in (('parent',C),('candidate',W)):
 m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');im=ElfImage(folder/'candidate.elf');im.load(m.uc);m.elf.symbols['entry']=im.symbols['mk61_m0_exp'];machines[label]=m;lowest[label]=SP
 def hook(uc,pc,size,user,label=label):lowest[label]=min(lowest[label],uc.reg_read(UC_ARM_REG_SP))
 m.uc.hook_add(UC_HOOK_CODE,hook)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)};rows=[]
for x,r in jobs.items():
 for state_name,state in states.items():
  frames={}
  for label,m in machines.items():
   m.uc.mem_write(0xd0000060,state);lowest[label]=SP;m.stack_lowest=SP
   got,_,cost=m.call('entry',x,count=True);assert got==int(r['candidate'],16)
   frames[label]=dict(SP_frame_bytes=SP-lowest[label],write_watermark_bytes=SP-m.stack_lowest,instructions=cost)
  assert frames['candidate']['SP_frame_bytes']<=frames['parent']['SP_frame_bytes']
  rows.append(dict(x=f'{x:016X}',SIO=state_name,frames=frames))
out=dict(status='PASS_FOCUSED_EXP_NEW_ENDPOINT_STACK_PARENT_CHILD_LIKE_FOR_LIKE',inputs=len(jobs),diagnostic_repeat_ARM_calls=4*len(jobs),calls_not_added_to_main_qualified_totals=True,MPFR_calls=0,
 maximum_frame_bytes={n:max(r['frames'][n]['SP_frame_bytes'] for r in rows) for n in machines},
 no_observed_new_stack_increase=True,observed_peaks_not_universal_bounds=True,rows=rows,hardware_accessed=False)
(W/'stack-deep-diagnostic.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='rows'},indent=2))
