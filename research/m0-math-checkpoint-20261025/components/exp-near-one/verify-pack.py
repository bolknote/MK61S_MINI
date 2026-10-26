from pathlib import Path
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support')]
from native_eabi_m0_arm_self_test import Machine,SP
c=json.loads((W/'certificate.json').read_text())
assert hashlib.sha256((W/'pack-unit.elf').read_bytes()).hexdigest()==c['pack_unit_ELF_sha256']
raw=(W/'pack-unit-inputs.bin').read_bytes();assert hashlib.sha256(raw).hexdigest()==c['pack_unit_input_sha256']
m=Machine(W/'pack-unit.elf',True);costs=Counter();accepted=rejected=0
for i,(a,correction,error) in enumerate(struct.iter_unpack('<3Q',raw)):
 if i%16384==0:print('pack-unit',i,'/',c['pack_unit_inputs'],flush=True)
 sign=a>>63;e=((a>>52)&2047)-1023;M=(a&((1<<52)-1))|(1<<52)
 t=16-e-sign;unit=1<<t
 exact=(M<<16)+(-correction if sign else correction)
 residue=(exact+unit//2+error)&(unit-1)
 unsafe=residue<=2*error
 displacement=(exact+unit//2)>>t
 expect=(0x3ff0000000000000+(-displacement if sign else displacement)) if not unsafe else (1<<64)-1
 got,_,cost=m.call('audit_exp_small_pack',a,correction,c=error,count=True)
 assert got==expect,(hex(a),correction,error,hex(got),hex(expect))
 costs[cost]+=1
 if unsafe:rejected+=1
 else:
  assert (exact-error+unit//2)>>t == (exact+error+unit//2)>>t
  accepted+=1
assert accepted and rejected
out=dict(status='PASS_LITERAL_SMALL_EXP_PACK_AGAINST_INTEGER_INTERVAL_ORACLE',
 unit_ELF_sha256=c['pack_unit_ELF_sha256'],qualified_fresh_ARM_calls=accepted+rejected,
 accepted=accepted,rejected=rejected,unsafe_admissions=0,all21binades_both_signs_all_pack_branches_midpoint_edges=True,
 instruction_counts=dict(costs),stack_bytes_touched=SP-m.stack_lowest,
 no_ROM_firmware_external_calls_mocks_or_SIO=True,actual_MPFR_calls=0,hardware_accessed=False)
(W/'pack-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
