"""Fresh parent cost for every remaining new-corpus speed loss."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-exp-directed-product-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q),str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
q=json.loads((W/'qualification.json').read_text())
rows=[r for r in q['remaining'] if r['parent_instructions'] is None]
m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
im=ElfImage(B/'candidate.elf');im.load(m.uc);m.elf.symbols['parent_exp']=im.symbols['mk61_m0_exp']
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
acquired=[];new=[]
for i,row in enumerate(rows):
 if i%256==0:print('remaining-parent',i,'/',len(rows),flush=True)
 state=states[row['SIO']];m.uc.mem_write(0xd0000060,state)
 got,_,cost=m.call('parent_exp',int(row['x'],16),count=True)
 assert got==int(row['candidate'],16)==int(row['expected'],16)
 after=bytes(m.uc.mem_read(0xd0000060,28))
 if row['SIO']=='DIRTY':assert after==state
 else:assert not(struct.unpack('<7I',after)[6]&2)
 r=dict(row,parent_instructions=cost);acquired.append(r)
 if cost<=r['Qfplib_instructions']:new.append(r)
out=dict(status='PASS_EVERY_REMAINING_NEW_CORPUS_LOSS_ALREADY_LOST_IN_PARENT',
 candidate_ELF_sha256=sha(W/'candidate.elf'),parent_ELF_sha256=sha(B/'candidate.elf'),
 fresh_parent_ARM_calls=len(rows),fresh_MPFR_calls=0,expected_reused_from_full_directed_qualification=True,
 remaining_state_rows=len(q['remaining']),known_parent_state_rows=len(q['remaining'])-len(rows),
 all_remaining_parent_states_now_bound=True,new_raw_losses=len({r['x'] for r in new}),
 wrong=0,hardware_accessed=False,rows=acquired,new=new)
(W/'remaining-parent-audit.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('rows','new')},indent=2))
assert not new
