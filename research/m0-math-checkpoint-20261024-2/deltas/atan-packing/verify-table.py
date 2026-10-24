"""Directed MPFR proof that every retained atan grid row has <=1/2 Q70 error."""
from pathlib import Path
from fractions import Fraction as F
import ctypes as C,hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q/'support'))
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,_Number
e=ElfImage(W/'candidate.elf');section=e.named_sections['.rodata'];data=e.bytes_at(section);assert len(data)==65*12
o=Oracle();lib=o.lib
lib.mpfr_mul_2si.argtypes=[C.POINTER(_Number),C.POINTER(_Number),C.c_long,C.c_int]
lib.mpfr_get_str.argtypes=[C.c_void_p,C.POINTER(C.c_long),C.c_int,C.c_size_t,C.POINTER(_Number),C.c_int];lib.mpfr_get_str.restype=C.c_void_p
lib.mpfr_free_str.argtypes=[C.c_void_p]
def fraction(number):
 exponent=C.c_long();p=lib.mpfr_get_str(None,C.byref(exponent),2,0,C.byref(number),0)
 try:digits=C.string_at(p).decode()
 finally:lib.mpfr_free_str(p)
 shift=exponent.value-len(digits)
 return F(int(digits,2)*(1<<shift)) if shift>=0 else F(int(digits,2),1<<(-shift))
rows=[]
for index in range(65):
 a=_Number();r=_Number();lib.mpfr_init2(C.byref(a),256);lib.mpfr_init2(C.byref(r),256)
 try:
  lib.mpfr_set_d(C.byref(a),index/64,0)
  low,mid,high=struct.unpack_from('<3I',data,index*12);q=low|(mid<<32)|(high<<64);bounds=[]
  for direction in (3,2):
   lib.mpfr_atan(C.byref(r),C.byref(a),direction);lib.mpfr_mul_2si(C.byref(r),C.byref(r),70,direction);bounds.append(fraction(r))
  assert F(q)-F(1,2)<=bounds[0]<=bounds[1]<=F(q)+F(1,2),index
  rows.append(dict(index=index,Q70=hex(q),absolute_error_bound=str(max(abs(F(q)-v) for v in bounds))))
 finally:lib.mpfr_clear(C.byref(a));lib.mpfr_clear(C.byref(r))
report=dict(status='PASS_ALL_65_TABLE_ROWS_HALF_Q70_DIRECTED_MPFR',MPFR_version=o.version,precision=256,cases=65,table_sha256=hashlib.sha256(data).hexdigest(),table_bytes_unchanged=True,rows=rows,hardware_accessed=False)
(W/'table-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
