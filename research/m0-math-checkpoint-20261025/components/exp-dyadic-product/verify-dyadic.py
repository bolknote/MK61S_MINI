from pathlib import Path
from collections import Counter
import hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path[:0]=[str(ROOT/'.build/m0-float-fma-qualification-20261023/support'),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
cert=json.loads((W/'certificate.json').read_text())
assert hashlib.sha256((W/'dyadic-unit.elf').read_bytes()).hexdigest()==cert['unit_ELF_sha256']
jobs=set(range(4096))
for bit in range(55):
 for offset in range(-5,6):
  x=(1<<bit)+offset
  if 0<=x<1<<54:jobs.add(x)
rng=random.Random(0xD1AD1C79)
for _ in range(65536):jobs.add(rng.getrandbits(54))
raw=b''.join(struct.pack('<Q',x) for x in sorted(jobs))
(W/'dyadic-unit-inputs.bin').write_bytes(raw)
m=Machine(W/'dyadic-unit.elf',True);costs=Counter()
for i,x in enumerate(sorted(jobs)):
 if i%16384==0:print('dyadic-unit',i,'/',len(jobs),flush=True)
 got,_,cost=m.call('audit_dyadic_product',x,count=True)
 assert got==((1<<62)*x+(1<<63))>>64
 costs[cost]+=1
out=dict(status='PASS_EXACT_DYADIC_HIGH_PRODUCT_LITERAL_ARM_UNIT',
 unit_ELF_sha256=cert['unit_ELF_sha256'],input_sha256=hashlib.sha256(raw).hexdigest(),
 actual_ARM_calls=len(jobs),exact128bit_integer_product_oracles=len(jobs),wrong=0,
 instruction_counts=dict(costs),stack_bytes_touched=SP-m.stack_lowest,
 ABI_SP_and_bounded_writes_checked_every_call=True,
 no_ROM_firmware_external_calls_or_mocks=True,hardware_accessed=False)
(W/'dyadic-unit-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
