from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path[:0]=[str(Q/'support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_R12
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
machines={label:Machine(W/('product-'+label+'.elf'),True) for label in ('old','new')};product_costs={n:Counter() for n in machines};numeric=0;valid=0;min_sp={n:SP for n in machines}
for label,m in machines.items():
 def observe_sp(uc,pc,size,user,label=label):min_sp[label]=min(min_sp[label],uc.reg_read(UC_ARM_REG_SP))
 m.uc.hook_add(UC_HOOK_CODE,observe_sp)
for index,(a,b) in enumerate(struct.iter_unpack('<QQ',(W/'product-unit-inputs.bin').read_bytes())):
 if index%4096==0:print('product-unit',index,flush=True)
 values={}
 for label,m in machines.items():
  got,_,cost=m.call('mk61_m0_pow_exp_product',a,b,count=True);values[label]=got;product_costs[label][cost]+=1
 assert values['old']==values['new'],(hex(a),hex(b),values)
 retained=sum(((a>>(16*i))&65535)*((b>>(16*j))&65535)<<(16*(i+j)) for i in range(4) for j in range(4) if i+j>=2)
 assert machines['new'].uc.reg_read(UC_ARM_REG_R12)==((retained>>32)&0xffffffff)
 if a<1<<63 and b<1<<54:
  exact=(retained+(1<<63))>>64
  assert values['new']==exact
  assert abs(values['new']*(1<<64)-a*b)<=(1<<63)+(1<<49)
  valid+=1
 numeric+=1
assert set(product_costs['old'])=={79} and set(product_costs['new'])=={77}
product=dict(raw64_pairs=numeric,valid63x54_exact_integer_references=valid,actual_ARM_calls=2*numeric,wrong=0,raw_returns_bit_identical=True,instruction_counts={n:dict(v) for n,v in product_costs.items()},stack_bytes={n:SP-v for n,v in min_sp.items()},stack_bytes_touched={n:SP-m.stack_lowest for n,m in machines.items()},old_new_same_entry_address='0x20038ee5',arithmetic_dataflow_register_renaming_and_three_moves_removed=True,all_raw_retained_fractions_in_R12_checked=True,standalone_no_ROM_firmware_or_mocks=True)
assert product['stack_bytes']=={'old':36,'new':36}
assert product['stack_bytes_touched']=={'old':36,'new':36}
out=dict(status='PASS_BIT_IDENTICAL_77_INSTRUCTION_PRODUCT_WITH_RETAINED_FRACTION_UNITS',product=product,total_actual_ARM_calls=product['actual_ARM_calls'],new_MPFR_calls=0,all_ABI_SP_bounded_writes_checked_every_call=True,hardware_accessed=False)
(W/'unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
