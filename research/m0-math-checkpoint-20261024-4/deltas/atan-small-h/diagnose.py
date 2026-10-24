"""Locate actual atan fallback and fixed-point midpoint margins."""
from pathlib import Path
from fractions import Fraction
import ctypes as C,hashlib,json,re,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from m0_mpfr_oracle import Oracle,_Number
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
m=Machine(ELF,True,bootrom=ROM);o=Oracle();lib=o.lib
lib.mpfr_atan.argtypes=[C.POINTER(_Number),C.POINTER(_Number),C.c_int]
lib.mpfr_mul_2si.argtypes=[C.POINTER(_Number),C.POINTER(_Number),C.c_long,C.c_int]
lib.mpfr_get_str.argtypes=[C.c_void_p,C.POINTER(C.c_long),C.c_int,C.c_size_t,C.POINTER(_Number),C.c_int];lib.mpfr_get_str.restype=C.c_void_p
lib.mpfr_free_str.argtypes=[C.c_void_p]
def exact_q70(raw):
 a=_Number();b=_Number();lib.mpfr_init2(C.byref(a),256);lib.mpfr_init2(C.byref(b),256)
 try:
  lib.mpfr_set_d(C.byref(a),struct.unpack('<d',struct.pack('<Q',raw))[0],0)
  lib.mpfr_atan(C.byref(b),C.byref(a),0);lib.mpfr_mul_2si(C.byref(b),C.byref(b),70,0)
  exponent=C.c_long();p=lib.mpfr_get_str(None,C.byref(exponent),2,0,C.byref(b),0)
  try:digits=C.string_at(p).decode()
  finally:lib.mpfr_free_str(p)
  return Fraction(int(digits,2),1<<len(digits))*(1<<exponent.value)
 finally:lib.mpfr_clear(C.byref(a));lib.mpfr_clear(C.byref(b))
def nearest(n,s):
 q,r=divmod(n,1<<s);return q+int(r>(1<<(s-1)) or (r==(1<<(s-1)) and q&1))
def product(a,b):return m.call('mk61_m0_product62',a,b)[0]
def table(name,index=0):
 matches=[v for n,v in m.elf.symbols.items() if name in n]
 if not matches and name=='refine_atan_half_pi':
  source=(P/'source/code/native_eabi_m0_refine_table.inc').read_text()
  initializer=re.search(r'refine_atan_half_pi\[[^\]]*\]\s*=\s*\{([^}]*)\}',source).group(1)
  words=[int(v.strip().rstrip('UuLl'),0) for v in initializer.split(',')];assert len(words)==3,words
  return words[0]|(words[1]<<32)|(words[2]<<64)
 assert len(matches)==1,(name,matches)
 a=matches[0]
 lo,mid,hi=struct.unpack('<3I',m.uc.mem_read(a+index*12,12));return lo|(mid<<32)|(hi<<64)
addresses={v&~1:n for n,v in m.elf.symbols.items() if n in ('mk61_m0_atan','atan_fast','atan_fast_ratio','atan_fast_reciprocal','atan_ratio_words','atan_refine','mk61_m0_cr_atan')}
records=[]
qualification=json.loads((ROOT/'.build/m0-atan-directional-ninth-20261024/qualification.json').read_text())
selected=[dict(operation='atan',x=f'{x:016X}') for x in sorted({int(r['x'],16)&((1<<63)-1) for r in qualification['remaining_slower_correct_Qfplib']})]
for row in selected:
 raw=int(row['x'],16);mag=raw&((1<<63)-1);e=(mag>>52)-1023;s=(mag&((1<<52)-1))|(1<<52);invert=mag>0x3ff0000000000000
 trace=[]
 def hook(uc,address,size,data):
  if address in addresses:
   trace.append(dict(function=addresses[address],registers=[uc.reg_read(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]))
 hnd=m.uc.hook_add(UC_HOOK_CODE,hook)
 try:got,_,count=m.call('mk61_m0_atan',raw,count=True)
 finally:m.uc.hook_del(hnd)
 if invert:
  seed=(1<<30)//(s>>37);index=(seed+(1<<(8+e)))>>(9+e)
  a=1<<(58-e);c=s*index;negative=a<c;numerator=abs(a-c)<<6;denominator=(s<<6)+(index<<(52-e))
 else:
  index=((s>>(45-e))+1)//2;a=s<<6;c=index<<(52-e);negative=a<c;n=abs(a-c);p=s*index
  numerator=n<<(5 if e==-6 else 6);denominator=((1<<63)|(p>>1)) if e==-6 else (1<<(58-e))+p
 h=m.call('atan_fast_ratio',numerator,denominator)[0] if numerator else 0
 z=nearest(product(h,h),8);c3=nearest(product(h,z),8)
 c5=(((c3>>17)*(z>>24))+(1<<28))>>29
 c7=(((c5>>3)*(z>>24))+(1<<42))>>43
 reduction=(c3+1)//3-((((c5>>3)*0xcccccccd)+(1<<30))>>31)+((c7+3)*2454267027>>34)
 q=table('refine_atan_table',index)+(-1 if negative else 1)*(h-reduction)
 if invert:q=table('refine_atan_half_pi')-q
 shift=q.bit_length()-53;tail=q&((1<<shift)-1);distance=abs(tail-(1<<(shift-1)))
 true=exact_q70(mag);error=Fraction(q)-true;herror=Fraction(h)-Fraction(numerator<<64,denominator)
 true_distance=abs(true-Fraction((q>>shift)*(1<<shift)+(1<<(shift-1))))
 records.append(dict(x=row['x'],output=f'{got:016X}',instructions=count,trace=trace,index=index,exponent=e,invert=invert,negative_reduction=negative,
                     numerator=hex(numerator),denominator=hex(denominator),h=hex(h),h_error=float(herror),q=hex(q),midpoint_distance_Q70=distance,q_error_Q70=float(error),
                     true_midpoint_distance_Q70=float(true_distance),source_radius=64,c3=c3,c5=c5,c7=c7))
result=dict(status='READ_ONLY_ACTUAL_V164_ATAN_DIAGNOSIS',ELF_sha256=hashlib.sha256(ELF.read_bytes()).hexdigest(),records=records,MPFR_version=o.version,hardware_accessed=False,canonical_or_frozen_changed=False)
(W/'diagnosis.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps([{k:v for k,v in r.items() if k not in ('trace','c3','c5','c7','numerator','denominator','h','q')} for r in records],indent=2))
