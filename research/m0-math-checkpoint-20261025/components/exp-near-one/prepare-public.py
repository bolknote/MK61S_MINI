"""New ordinary exp and actual output-midpoint preimage neighbors."""
from pathlib import Path
import ctypes as C,hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q/'support'))
from m0_mpfr_oracle import Oracle,_Number,bits
oracle=Oracle();lib=oracle.lib;pointer=C.POINTER(_Number)
lib.mpfr_set_ui.argtypes=[pointer,C.c_ulong,C.c_int]
lib.mpfr_mul_2si.argtypes=[pointer,pointer,C.c_long,C.c_int]
jobs={};logs=0
def add(x,group):
 if 0<=x<1<<64:jobs.setdefault(x,group)
def log_dyadic(n,shift):
 global logs
 x=_Number();lib.mpfr_init2(C.byref(x),64)
 lib.mpfr_set_ui(C.byref(x),n,0);lib.mpfr_mul_2si(C.byref(x),C.byref(x),shift,0)
 try:
  p=128
  while p<=16384:
   outputs=[]
   for direction in (3,2):
    v=_Number();lib.mpfr_init2(C.byref(v),p)
    try:lib.mpfr_log(C.byref(v),C.byref(x),direction);outputs.append(bits(lib.mpfr_get_d(C.byref(v),0)))
    finally:lib.mpfr_clear(C.byref(v))
   if outputs[0]==outputs[1]:logs+=1;return outputs[0]
   p*=2
  raise AssertionError('MPFR log preimage undecided')
 finally:lib.mpfr_clear(C.byref(x))
rng=random.Random(0x51A11F679)
for e in range(-32,-11):
 for negative in (0,1):
  width=e+52+negative
  for _ in range(64):
   displacement=(1<<width)|rng.getrandbits(width)
   numerator=(1<<54)-(2*displacement+1) if negative else (1<<53)+(2*displacement+1)
   center=log_dyadic(numerator,-54 if negative else -53)
   for step in (-2,-1,0,1,2):add(center+step,'new_small_actual_output_midpoint_log_preimages')
  for c in range(32,64):
   for low in (0,1,(1<<47)-2,(1<<47)-1):
    M=(c<<47)|low
    add((negative<<63)|((e+1023)<<52)|(M-(1<<52)),'new_all_coarse_fifth_class_boundaries')
raw=b''.join(struct.pack('<Q',x) for x in jobs)
(W/'public-new-inputs.bin').write_bytes(raw)
(W/'public-new-groups.json').write_text(json.dumps(list(jobs.values()))+'\n')
out=dict(status='PREPARED_NEAR_ONE_BOUNDARY_CORPUS_NOT_RUNTIME_REFERENCES',inputs=len(jobs),MPFR_directed_log_preimage_generations=logs,MPFR_version=oracle.version,log_generation_not_added_to_exp_reference_count=True,input_sha256=hashlib.sha256(raw).hexdigest(),hardware_accessed=False)
(W/'public-input-preparation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
