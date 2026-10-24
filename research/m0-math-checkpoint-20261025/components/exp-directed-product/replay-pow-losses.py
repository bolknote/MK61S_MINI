"""Re-profile every previously losing pow state after a monotone callee change.

The other old states need no new execution: the one changed straight-line
callee is value/ABI equivalent and2instructions cheaper for every raw input.
This is a targeted loss replay, not a fresh111912-pair full acquisition.
"""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';B=ROOT/'.build/m0-exp-cached-product-20261024';S=ROOT/'.build/m0-pow-square-ordinary-20261024';R=ROOT/'.build/m0-pow-rsqrt-asm-20261024';Q=ROOT/'.build/m0-float-fma-qualification-20261023';D=ROOT/'.build/m0-exp-dyadic-product-20261024'
sys.path[:0]=[str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
for folder in (B,S,R):
 im=ElfImage(folder/'candidate.elf');im.load(m.uc)
 if folder==R:m.elf.symbols.update({n:a for n,a in im.symbols.items() if n.startswith('mk61_m0_pow_')})
oldim=ElfImage(B/'candidate.elf');olds=oldim.named_sections['.product_ram'];assert bytes(m.uc.mem_read(olds[3],168))==oldim.bytes_at(olds)
im=ElfImage(W/'candidate.elf');m.uc.mem_write(olds[3],im.bytes_at(im.named_sections['.product_ram']))
calls=[]
def hook(uc,pc,size,user):
 a=uc.reg_read(UC_ARM_REG_R0)|(uc.reg_read(UC_ARM_REG_R1)<<32);b=uc.reg_read(UC_ARM_REG_R2)|(uc.reg_read(UC_ARM_REG_R3)<<32)
 assert a<1<<63 and b<1<<54
 calls.append((a,b))
m.uc.hook_add(UC_HOOK_CODE,hook,begin=olds[3],end=olds[3])
previous=json.loads((D/'pow-loss-replay.json').read_text());assert previous['remaining_pairs_after']==7901
for row in previous['rows']:
 row['instructions']['candidate']=row['fresh_candidate']['candidate_instructions']
 row['outputs']['candidate']=row['fresh_candidate']['candidate']
jobs={}
for r in previous['rows']:jobs.setdefault((r['x'],r['y'],r['SIO']),r)
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)};acquired={}
for index,(key,row) in enumerate(jobs.items()):
 if index%256==0:print('pow-loss',index,'/',len(jobs),flush=True)
 state=states[row['SIO']];m.uc.mem_write(0xd0000060,state);calls.clear()
 got,_,cost=m.call('_ZN12compact_math3powEdd',int(row['x'],16),int(row['y'],16),count=True)
 assert got==int(row['outputs']['candidate'],16)==int(row['expected'],16)
 assert cost==row['instructions']['candidate']-2*len(calls),(key,cost,row['instructions'],len(calls))
 after=bytes(m.uc.mem_read(0xd0000060,28))
 if row['SIO']=='DIRTY':assert after==state
 else:assert not(struct.unpack('<7I',after)[6]&2)
 acquired[key]=dict(candidate=f'{got:016X}',candidate_instructions=cost,product_calls=len(calls))
rows=[];remaining=[]
for old in previous['rows']:
 fresh=acquired[old['x'],old['y'],old['SIO']]
 row=dict(old,previous_candidate_instructions=old['instructions']['candidate'],fresh_candidate=fresh)
 rows.append(row)
 if fresh['candidate_instructions']>old['instructions']['Qfplib']:remaining.append(row)
oldpairs={(r['x'],r['y']) for r in rows if r['previous_candidate_instructions']>r['instructions']['Qfplib']};newpairs={(r['x'],r['y']) for r in remaining}
fixed=sorted(oldpairs-newpairs)
out=dict(status='PASS_ALL_PREVIOUS_EXPANDED_POW_LOSSES_REPLAYED_AFTER_MONOTONE_PRODUCT_CHANGE',candidate_product_ELF_sha256=sha(W/'candidate.elf'),parent_accepted_pow_ELF_sha256=sha(R/'candidate.elf'),pinned_parent_remaining_sha256=sha(D/'pow-loss-replay.json'),
 inherited_full_parent_union_pairs=111912,inherited_parent_remaining_pairs=7901,
 replayed_reference_state_variants_including_prior_ties=len(rows),current_parent_losing_reference_state_variants=sum(r['previous_candidate_instructions']>r['instructions']['Qfplib'] for r in rows),fresh_candidate_state_calls=len(jobs),fresh_MPFR_calls=0,
 old_MPFR_bits_reference_costs_and_numerical_correctness_inherited_not_new=True,
 no_full111912_pair_rerun_claim=True,all_new_raw_bits_match_parent_expected=True,all_new_costs_parent_minus2_per_product_call=True,
 all_other_old_states_cannot_regress_by_proved_value_ABI_equivalence_and_constant_cost_reduction=True,
 current_loss_pairs_scope_only=True,three_prior_raw_pair_ties_included_for_strict_improvement_check=True,remaining_pairs_after=len(newpairs),fixed_pairs=len(fixed),fixed_pair_values=fixed,new_raw_losses=0,wrong=0,
 observed_stack_bytes=SP-m.stack_lowest,hardware_accessed=False,rows=rows,remaining=remaining)
(W/'pow-loss-replay.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ('rows','remaining','fixed_pair_values')},indent=2))
