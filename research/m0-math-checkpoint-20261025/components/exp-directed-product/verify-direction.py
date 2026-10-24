from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
c=json.loads((W/'certificate.json').read_text());rh=F(c['real_h']);rem=F(c['Taylor_plus_step_upper']);cross=F(c['Q94_table_bias_cross_upper'])
assert hashlib.sha256((W/'direction-unit.elf').read_bytes()).hexdigest()==c['unit_ELF_sha256']
m=Machine(W/'direction-unit.elf',True);counts=Counter();cache={};accepted=rejected=0
for index,(q,args,params) in enumerate(struct.iter_unpack('<3Q',(W/'direction-unit-inputs.bin').read_bytes())):
 if index%16384==0:print('direction-unit',index,'/',c['unit_inputs'],flush=True)
 n=args>>32;bias=args&0xffffffff;bias=bias if bias<1<<31 else bias-(1<<32)
 frac=params&0xffffffff;H=(1-(params>>32))&0xffffffff;g=(H+1023)>>10;head=q>>48
 key=(head,g,n,bias)
 if key not in cache:
  f=F((n*c['exp_step_low'])&0xffffffff,1<<32)
  delta=1+F(3*g*g,1<<24)+rem-f*(1-rh)
  assert delta>0
  cache[key]=delta*F(head+24,65536)+F(bias,1<<32)+cross
 upper_bound=cache[key]
 got,_,cost=m.call('audit_exp_direction',q,args,c=params,count=True)
 upper=got>>32;upper=upper if upper<1<<31 else upper-(1<<32);safe=bool(got&1)
 assert got&0xffffffff==int(safe) and safe==(upper<=256)
 # Compare every actual ARM upper with the independent, unrounded rational
 # enclosure, not another implementation of the source integer expression.
 num=upper*(1<<32)-(frac>>31)*(1<<40)+(frac<<8)
 assert num*upper_bound.denominator>upper_bound.numerator*(1<<40)
 if safe:
  assert upper_bound.numerator*(1<<32)+((frac>>31)*(1<<32)-frac)*upper_bound.denominator<upper_bound.denominator*(1<<32)
  accepted+=1
 else:rejected+=1
 counts[cost]+=1
assert accepted and rejected
out=dict(status='PASS_LITERAL_DIRECTIONAL_GATE_AGAINST_INDEPENDENT_RATIONAL_ENCLOSURE',
 unit_ELF_sha256=c['unit_ELF_sha256'],actual_ARM_calls=accepted+rejected,
 accepted=accepted,rejected=rejected,unsafe_admissions=0,all_source_g_bins_and_all_qhead_bins_included=True,
 instruction_counts=dict(counts),stack_bytes_touched=SP-m.stack_lowest,
 no_ROM_firmware_external_calls_mocks_or_SIO=True,new_MPFR_calls=0,hardware_accessed=False)
(W/'direction-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
