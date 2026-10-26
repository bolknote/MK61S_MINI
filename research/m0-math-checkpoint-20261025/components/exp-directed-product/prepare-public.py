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
rng=random.Random(0xD1EEC779)
for _ in range(1024):add(bits(rng.uniform(-745.2,710.0)),'new_ordinary_uniform')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
im=ElfImage(W/'candidate.elf');name=next(n for n in im.symbols if 'exp_table' in n and im.sizes.get(n)==4096);address=im.symbols[name]
sec=next(s for s in im.named_sections.values() if s[3]<=address<s[3]+s[5]);table=struct.unpack('<512Q',im.bytes_at(sec)[address-sec[3]:address-sec[3]+4096])
for i in range(1,512):
 k=(i*37)%1024;M=table[i]>>10
 center=log_dyadic(2*M-1,k-53)
 for step in (-2,-1,0,1,2):add(center+step,'all_nonzero_table_row_lower_midpoint_preimages')
for _ in range(1024):
 M=(1<<52)|rng.getrandbits(52);k=rng.randrange(1024)
 center=log_dyadic(2*M+1,k-53)
 for step in (-2,-1,0,1,2):add(center+step,'positive_normal_actual_midpoint_preimages')
for i in range(128):
 d=rng.getrandbits(40)
 numerator=(1<<54)-(2*d+1) if i&1 else (1<<53)+(2*d+1)
 center=log_dyadic(numerator,-54 if i&1 else -53)
 for step in (-2,-1,0,1,2):add(center+step,'small_actual_midpoint_preimages')
for i in range(256):
 M=(1<<52)|rng.getrandbits(52);k=(-1074,-1022,-512,-1,0,1,512,1023,1024)[i%9]
 center=log_dyadic(2*M+1,k-53)
 for step in (-2,-1,0,1,2):add(center+step,'broad_endpoint_actual_midpoint_preimages')
raw=b''.join(struct.pack('<Q',x) for x in jobs)
(W/'public-new-inputs.bin').write_bytes(raw)
(W/'public-new-groups.json').write_text(json.dumps(list(jobs.values()))+'\n')
out=dict(status='PREPARED_NEW_PUBLIC_EXP_CORPUS_NOT_RUNTIME_REFERENCES',inputs=len(jobs),MPFR_directed_log_preimage_generations=logs,MPFR_version=oracle.version,log_generation_not_added_to_exp_reference_count=True,input_sha256=hashlib.sha256(raw).hexdigest(),hardware_accessed=False)
(W/'public-input-preparation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
