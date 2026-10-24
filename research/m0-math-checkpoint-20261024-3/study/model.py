"""Study a cold ninth-order correction; no runtime implementation is changed."""
from pathlib import Path
from fractions import Fraction as F
import ctypes as C,hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023';BASE=ROOT/'.build/m0-atan-residual-original-goal-20261024'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from m0_mpfr_oracle import Oracle,_Number
from oracles import round_ratio
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(BASE/'result.json')=='e047da61a015906cac349efa0331625bd625c53a7e42de622fb94268225d669c'
machine=Machine(P/'firmware/mk61s-picocalc-pico-h.elf',True,bootrom=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
oracle=Oracle();lib=oracle.lib;S=1<<70
lib.mpfr_atan.argtypes=[C.POINTER(_Number),C.POINTER(_Number),C.c_int]
lib.mpfr_set_ui.argtypes=[C.POINTER(_Number),C.c_ulong,C.c_int]
lib.mpfr_mul_2si.argtypes=[C.POINTER(_Number),C.POINTER(_Number),C.c_long,C.c_int]
lib.mpfr_get_str.argtypes=[C.c_void_p,C.POINTER(C.c_long),C.c_int,C.c_size_t,C.POINTER(_Number),C.c_int];lib.mpfr_get_str.restype=C.c_void_p
lib.mpfr_free_str.argtypes=[C.c_void_p]
input_number=_Number();output_number=_Number()
lib.mpfr_init2(C.byref(input_number),256);lib.mpfr_init2(C.byref(output_number),256)
def fraction(number):
 exponent=C.c_long();p=lib.mpfr_get_str(None,C.byref(exponent),2,0,C.byref(number),0)
 try:digits=C.string_at(p).decode()
 finally:lib.mpfr_free_str(p)
 out=F(int(digits,2),1<<len(digits))
 return out*(1<<exponent.value) if exponent.value>=0 else out/F(1<<(-exponent.value))
def atan_interval(raw=None,h=None):
 if raw is not None:lib.mpfr_set_d(C.byref(input_number),struct.unpack('<d',struct.pack('<Q',raw))[0],0)
 else:
  lib.mpfr_set_ui(C.byref(input_number),h,0)
  lib.mpfr_mul_2si(C.byref(input_number),C.byref(input_number),-70,0)
 out=[]
 for direction in (3,2):
  lib.mpfr_atan(C.byref(output_number),C.byref(input_number),direction)
  lib.mpfr_mul_2si(C.byref(output_number),C.byref(output_number),70,direction)
  out.append(fraction(output_number))
 assert out[0]<=out[1]
 return out
calls=0
def product(a,b):
 global calls
 calls+=1
 return machine.call('mk61_m0_product62',a,b)[0]
def right(a,b):
 q,r=divmod(a,1<<b);half=1<<(b-1)
 return q+int(r>half or (r==half and q&1))
def signed_nearest(n,d):
 q=(abs(n)+d//2)//d
 return -q if n<0 else q
def div5_small(n):
 q=((abs(n)+2)*13108)>>16
 return -q if n<0 else q
for n in range(-64,65):assert div5_small(n)==signed_nearest(n,5)
for n in range(130):assert ((n+4)*7282)>>16==(n+4)//9
def mod3_remainder(c3):
 lo=c3&0xffffffff;hi=c3>>32
 f=(lo&65535)+(lo>>16)+hi
 f=(f&255)+(f>>8);assert f<=1278
 q=f*21846>>16;r=f-3*q;assert r in (0,1,2)
 return r if r<2 else -1
def mod7_remainder(c7):
 f=(c7>>9)+(c7&511);assert f<=8702
 q=f*9363>>16;r=f-7*q;assert 0<=r<=6
 return r if r<=3 else r-7
def polynomial(h,z=None,c3=None,c5=None,c7=None):
 if z is None:z=right(product(h,h),8)
 if c3 is None:c3=right(product(h,z),8)
 if c5 is None:c5=((c3>>17)*(z>>24)+(1<<28))>>29
 if c7 is None:c7=((c5>>3)*(z>>24)+(1<<42))>>43
 third=(c3+1)//3
 fifth=((c5>>3)*0xCCCCCCCD+(1<<30))>>31
 seventh=(c7+3)*2454267027>>34
 old=h-third+fifth-seventh
 r5=c5-5*fifth;assert -4<=r5<=9,r5
 m1=(c3>>33)*((z&((1<<24)-1))>>8)
 m2=((c3&((1<<17)-1))>>1)*(z>>40)
 missing=(m1+m2+(1<<28))>>29
 delta_fifth=div5_small(r5+missing)
 r5+=missing-5*delta_fifth;assert -2<=r5<=2
 c9=(((c7>>6)*(z>>40))+(1<<23))>>24
 assert c9<=128,c9
 ninth=(c9+4)*7282>>16;r9=c9-9*ninth
 r3=mod3_remainder(c3);r7=mod7_remainder(c7)
 assert r3==c3-3*third and r7==c7-7*seventh
 bias=-105*r3+63*r5-45*r7+35*r9
 assert abs(bias)<=506
 correction=(int(abs(bias)>=158)+int(abs(bias)>=473))*(-1 if bias<0 else 1)
 assert correction==signed_nearest(bias,315)
 delta=delta_fifth+ninth+correction
 return old,old+delta,dict(poly_delta=delta,missing_fifth=missing,delta_fifth=delta_fifth,c9=c9,ninth=ninth,r3=r3,r5=r5,r7=r7,r9=r9,bias_numerator=bias,bias_correction=correction,z=z)

# A conservative, exact error bound for the proposed polynomial.
cap=F(1,128);ez=F(1,2)+F(13,512)
e3=F(1,2)+F(13,512)+cap*ez
old_e5=(F(1,2)+cap**2*e3+cap**3*ez+e3*ez/S+
        ((1<<17)-1)*(S*cap**2+ez)/S+((1<<24)-1)*(S*cap**3+e3)/S)
e7=(F(1,2)+cap**2*old_e5+cap**5*ez+old_e5*ez/S+
    7*(S*cap**2+ez)/S+((1<<24)-1)*(S*cap**5+old_e5)/S)
e5=1+F(1,2048)+cap**2*e3+cap**3*ez+e3*ez/S
e9=F(1,2)+F(1,128)+cap**2*e7+cap**7*ez+e7*ez/S
omitted=S*cap**11/(11*(1-cap**2))
poly_bound=F(1,2)+e3/3+e5/5+e7/7+e9/9+omitted
rounded_ratio_bound=F(1,2)+F(35,1<<20)
all_geometry_bound=poly_bound+rounded_ratio_bound+1+33*(cap+F(33,S))**2
assert poly_bound<F(101,100)
assert all_geometry_bound<3
records=[];start=time.monotonic()
try:
 for original in json.loads((BASE/'diagnosis.json').read_text())['records']:
  raw=int(original['x'],16);h=int(original['h'],16);n=int(original['numerator'],16);d=int(original['denominator'],16)
  z=right(product(h,h),8)
  old,new,parts=polynomial(h,z,original['c3'],original['c5'],original['c7'])
  residual=(n<<64)-h*d
  top=abs(residual)>>38;den=d>>38
  delta=(top+(den>>1))//den
  if residual<0:delta=-delta
  q=int(original['q'],16)
  direction=-1 if original['negative_reduction']!=original['invert'] else 1
  result=q+direction*(delta+parts['poly_delta'])
  lower,upper=atan_interval(raw=raw)
  error=max(abs(F(result)-lower),abs(F(result)-upper))
  shift=q.bit_length()-53;tail=result&((1<<shift)-1);distance=abs(tail-(1<<(shift-1)))
  got=round_ratio(result,1,-70,64,False);expected=oracle.reference('atan',raw)
  assert error<all_geometry_bound,(original['x'],float(error),float(all_geometry_bound))
  records.append(dict(x=original['x'],exponent=original['exponent'],invert=original['invert'],
                      error_Q70=float(error),midpoint_distance_Q70=distance,model_bits=f'{got:016X}',expected_bits=f'{expected:016X}',
                      raw_correct=got==expected,radius3_accepts=distance>=3,quotient_delta=delta,**parts))
 jobs={0,1,2,(1<<62)-1,1<<62,(1<<62)+1}
 for bit in range(63):
  for offset in (-1,0,1):
   if 0<=(1<<bit)+offset<(1<<63):jobs.add((1<<bit)+offset)
 rng=random.Random(0xA7A90003)
 for _ in range(4096):jobs.add(rng.randrange(1<<63))
 jobs={h for h in jobs if h<F(S,128)-S//(1<<24)}
 max_error=F(0);digest=hashlib.sha256()
 for h in sorted(jobs):
  old,new,parts=polynomial(h)
  lower,upper=atan_interval(h=h)
  error=max(abs(F(new)-lower),abs(F(new)-upper));assert error<poly_bound,(hex(h),float(error))
  max_error=max(max_error,error);digest.update(struct.pack('<QQ',h,new))
finally:
 lib.mpfr_clear(C.byref(input_number));lib.mpfr_clear(C.byref(output_number))
report=dict(status='PASS_EXPLORATORY_INTEGER_POLYNOMIAL_MODEL_NOT_ARM_RUNTIME',records=records,
            independent_reduced_h_samples=len(jobs),actual_ARM_product_calls=calls,
            polynomial_error_bound=str(poly_bound),polynomial_error_bound_float=float(poly_bound),
            quotient_rounding_error_bound=str(rounded_ratio_bound),all_geometry_error_bound=str(all_geometry_bound),
            all_geometry_error_bound_float=float(all_geometry_bound),strict_candidate_radius_Q70=3,
            observed_polynomial_error_max_Q70=float(max_error),reduced_h_transcript_sha256=digest.hexdigest(),
            MPFR_version=oracle.version,parent_result_sha256=sha(BASE/'result.json'),
            no_new_runtime_implementation=True,instruction_speed_not_measured=True,
            physical_hardware_accessed=False,canonical_or_frozen_changed=False,goal_complete=False,
            elapsed_seconds=time.monotonic()-start)
(W/'model.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
print(json.dumps([{k:r[k] for k in ('x','error_Q70','midpoint_distance_Q70','raw_correct','radius3_accepts','poly_delta','quotient_delta')} for r in records],indent=2))
