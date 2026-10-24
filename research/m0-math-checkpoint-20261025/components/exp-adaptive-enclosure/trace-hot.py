from pathlib import Path
import difflib,json,re,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];C=ROOT/'.build/m0-exp-tiny-log-midpoint-20261024';P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE
result={}
for label,folder in (('parent',C),('candidate',W)):
 im=ElfImage(folder/'candidate.elf');m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');im.load(m.uc);m.elf.symbols['entry']=im.symbols['mk61_m0_exp'];entry=im.symbols['mk61_m0_exp']&~1;end=entry+im.sizes['mk61_m0_exp'];code={}
 for line in (folder/'candidate.dis').read_text().splitlines():
  parts=line.split('\t')
  if len(parts)>=3 and parts[0].strip().endswith(':'):
   try:a=int(parts[0].strip()[:-1],16)
   except ValueError:continue
   mnemonic=parts[2].split('@')[0].strip();code[a]=mnemonic
 trace=[]
 def hook(uc,pc,size,data):
  if entry<=pc<end:
   s=code.get(pc,'?')
   normalized=s
   if s.startswith('b'):normalized=s.split()[0]
   if '[pc,' in normalized:normalized=re.sub(r'#\d+','#lit',normalized)
   trace.append(dict(offset=pc-entry,text=s,normalized=normalized))
 h=m.uc.hook_add(UC_HOOK_CODE,hook);got,_,cost=m.call('entry',0x3fb1b32892630b90,count=True);m.uc.hook_del(h)
 result[label]=dict(result=f'{got:016X}',instructions=cost,trace=trace)
a,b=[result[n]['trace'] for n in ('parent','candidate')]
changes=[]
for op,i,j,k,l in difflib.SequenceMatcher(a=[v['normalized'] for v in a],b=[v['normalized'] for v in b],autojunk=False).get_opcodes():
 if op!='equal':changes.append(dict(op=op,parent=a[max(0,i-2):min(len(a),j+2)],candidate=b[max(0,k-2):min(len(b),l+2)]))
out=dict(status='DIAGNOSTIC_NORMAL_PATH_TRACE_NOT_QUALIFICATION',parent_instructions=result['parent']['instructions'],candidate_instructions=result['candidate']['instructions'],changes=changes,hardware_accessed=False)
(W/'hot-trace.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
