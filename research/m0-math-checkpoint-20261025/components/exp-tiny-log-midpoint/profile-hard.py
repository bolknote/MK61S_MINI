"""Diagnostic two original exp losses; not pooled with qualification."""
from pathlib import Path
from collections import Counter
import hashlib,json,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE
im=ElfImage(W/'candidate.elf')
m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');im.load(m.uc)
m.elf.symbols['candidate_exp']=im.symbols['mk61_m0_exp']
refine=next(n for n in im.symbols if 'exp_refine' in n);refine_start=im.symbols[refine]&~1;refine_end=refine_start+im.sizes[refine]
entry=im.symbols['mk61_m0_exp']&~1;end=entry+im.sizes['mk61_m0_exp'];rows=[]
for x,expected in ((0x4085f424184f6dc5,0x7f46ec297b4bf167),(0xc041265824e2113c,0x3cd6e1fb162dabc8)):
 counter=Counter();first=[];calls=[]
 def observe(uc,pc,size,user):
  counter['total']+=1
  if pc==refine_start:
   calls.append(counter['total']);first.append(counter['total']-1)
  if refine_start<=pc<refine_end:counter['inside_refine_body']+=1
  elif entry<=pc<end:counter['inside_public_body']+=1
  else:counter['other_helpers']+=1
 h=m.uc.hook_add(UC_HOOK_CODE,observe)
 got,_,cost=m.call('candidate_exp',x,count=True);m.uc.hook_del(h)
 assert got==expected and counter['total']==cost
 rows.append(dict(x=f'{x:016X}',output=f'{got:016X}',instructions=cost,first_refine_entry_after_instructions=first,parts=dict(counter)))
out=dict(status='DIAGNOSTIC_ORIGINAL_TWO_EXP_REFINEMENTS_NOT_QUALIFICATION',candidate_ELF_sha256=hashlib.sha256((W/'candidate.elf').read_bytes()).hexdigest(),fresh_diagnostic_ARM_calls=2,expected_from_pinned_prior_directed_qualification=True,no_new_MPFR_claim=True,rows=rows,hardware_accessed=False)
(W/'hard-refine-profile.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
