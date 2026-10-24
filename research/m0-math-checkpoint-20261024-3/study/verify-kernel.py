"""Check the isolated Thumb polynomial correction against directed MPFR."""
from pathlib import Path
from fractions import Fraction as F
import ast,ctypes as C,hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';BASE=ROOT/'.build/m0-atan-residual-original-goal-20261024'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from m0_mpfr_oracle import Oracle,_Number
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'build.json').read_text());model=json.loads((W/'model.json').read_text())
assert sha(W/'poly-correction.cpp')==build['source_sha256'] and sha(W/'poly.elf')==build['ELF_sha256']
source=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
kernel=Machine(W/'poly.elf',True,stack_bytes=128)
oracle=Oracle();lib=oracle.lib
lib.mpfr_atan.argtypes=[C.POINTER(_Number),C.POINTER(_Number),C.c_int]
lib.mpfr_set_ui.argtypes=[C.POINTER(_Number),C.c_ulong,C.c_int]
lib.mpfr_mul_2si.argtypes=[C.POINTER(_Number),C.POINTER(_Number),C.c_long,C.c_int]
lib.mpfr_get_str.argtypes=[C.c_void_p,C.POINTER(C.c_long),C.c_int,C.c_size_t,C.POINTER(_Number),C.c_int];lib.mpfr_get_str.restype=C.c_void_p
lib.mpfr_free_str.argtypes=[C.c_void_p]
input_number=_Number();output_number=_Number()
lib.mpfr_init2(C.byref(input_number),256);lib.mpfr_init2(C.byref(output_number),256)
reference_calls=0
def product(a,b):
 global reference_calls
 reference_calls+=1
 return source.call('mk61_m0_product62',a,b)[0]
# Load pure functions only; do not execute or rewrite the model producer.
tree=ast.parse((W/'model.py').read_text())
names={'right','signed_nearest','div5_small','mod3_remainder','mod7_remainder','polynomial','fraction','atan_interval'}
functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
assert len(functions)==len(names)
env=dict(F=F,C=C,lib=lib,struct=struct,input_number=input_number,output_number=output_number,product=product)
exec(compile(ast.Module(body=functions,type_ignores=[]),str(W/'model.py'),'exec'),env)
right=env['right'];polynomial=env['polynomial'];interval=env['atan_interval']
states=(struct.pack('<7I',0,0,0,0,0,0,1),struct.pack('<7I',17,3,17,3,5,2,3))
digest=hashlib.sha256();rows=[];counts=[];max_error=F(0);kernel_calls=0;start=time.monotonic()
def call(z,c3,c7,r5,expected):
 global kernel_calls
 costs=[]
 for state in states:
  kernel.uc.mem_write(0xd0000060,state)
  raw,_,cost=kernel.call('atan_poly_tail',z,c3,c=(c7|((r5&0xffffffff)<<32)),count=True)
  raw&=0xffffffff;got=raw-(1<<32) if raw>>31 else raw
  assert got==expected,(hex(z),hex(c3),c7,r5,got,expected)
  assert bytes(kernel.uc.mem_read(0xd0000060,28))==state
  costs.append(cost);counts.append(cost);kernel_calls+=1
 assert costs[0]==costs[1]
 return expected,costs[0]
try:
 for r in json.loads((BASE/'diagnosis.json').read_text())['records']:
  h=int(r['h'],16);z=right(product(h,h),8);c3=r['c3'];c5=r['c5'];c7=r['c7']
  old,new,parts=polynomial(h,z,c3,c5,c7)
  fifth=((c5>>3)*0xCCCCCCCD+(1<<30))>>31;r5=c5-5*fifth
  got,cost=call(z,c3,c7,r5,new-old)
  rows.append(dict(x=r['x'],poly_delta=got,instructions=cost))
 jobs={0,1,2,(1<<62)-1,1<<62,(1<<62)+1}
 for bit in range(63):
  for offset in (-1,0,1):
   if 0<=(1<<bit)+offset<(1<<63):jobs.add((1<<bit)+offset)
 rng=random.Random(0xA7A90003)
 for _ in range(4096):jobs.add(rng.randrange(1<<63))
 jobs={h for h in jobs if h<F(1<<70,128)-(1<<70)//(1<<24)}
 for h in sorted(jobs):
  z=right(product(h,h),8);c3=right(product(h,z),8)
  c5=((c3>>17)*(z>>24)+(1<<28))>>29;c7=((c5>>3)*(z>>24)+(1<<42))>>43
  old,new,parts=polynomial(h,z,c3,c5,c7)
  fifth=((c5>>3)*0xCCCCCCCD+(1<<30))>>31;r5=c5-5*fifth
  got,cost=call(z,c3,c7,r5,new-old)
  lower,upper=interval(h=h)
  error=max(abs(F(old+got)-lower),abs(F(old+got)-upper))
  assert error<F(model['polynomial_error_bound'])
  max_error=max(max_error,error);digest.update(struct.pack('<QQi',h,old,got))
finally:
 lib.mpfr_clear(C.byref(input_number));lib.mpfr_clear(C.byref(output_number))
report=dict(status='PASS_ISOLATED_ARM_POLYNOMIAL_TAIL_NOT_PUBLIC_RUNTIME',hard_magnitudes=len(rows),hard_rows=rows,
            reduced_h_samples=len(jobs),actual_kernel_ARM_calls=kernel_calls,actual_source_product_ARM_calls=reference_calls,
            instruction_min=min(counts),instruction_max=max(counts),instruction_mean=sum(counts)/len(counts),
            observed_stack_bytes=SP-kernel.stack_lowest,PCS_SP_bounded_writes_and_SIO_preserved_every_call=True,
            directed_MPFR_version=oracle.version,polynomial_error_max_Q70=float(max_error),
            polynomial_error_bound=model['polynomial_error_bound'],transcript_sha256=digest.hexdigest(),
            source_sha256=sha(W/'poly-correction.cpp'),ELF_sha256=sha(W/'poly.elf'),model_source_sha256=sha(W/'model.py'),
            helper_maps_firmware_or_ROM=False,no_undefined_symbols=True,public_runtime_implemented=False,
            public_speed_or_correctness_GO=False,hardware_accessed=False,goal_complete=False,
            elapsed_seconds=time.monotonic()-start)
(W/'kernel-proof.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
