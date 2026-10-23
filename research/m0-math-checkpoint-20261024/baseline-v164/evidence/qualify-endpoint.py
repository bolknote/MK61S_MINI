"""Check actual fixed-point endpoint enclosures and all four public results."""
import ctypes as C
import hashlib,json,random,re,struct,sys
from pathlib import Path
root=Path.cwd();work=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,SP,bits,real
from m0_mpfr_oracle import Oracle,_Number
from unicorn import UC_HOOK_CODE
elf=work/'firmware/mk61s-picocalc-pico-h.elf'
m=Machine(elf,True,stack_bytes=16384,instruction_budget=200000000,
    bootrom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin')
oracle=Oracle();lib=oracle.lib;pointer=C.POINTER(_Number)
lib.mpfr_mul_2si.argtypes=[pointer,pointer,C.c_long,C.c_int];lib.mpfr_mul_2si.restype=C.c_int
lib.mpfr_set_str.argtypes=[pointer,C.c_char_p,C.c_int,C.c_int];lib.mpfr_set_str.restype=C.c_int
lib.mpfr_cmp.argtypes=[pointer,pointer];lib.mpfr_cmp.restype=C.c_int
numbers=[_Number() for _ in range(5)]
for number in numbers:lib.mpfr_init2(C.byref(number),192)
arg,lo,hi,lower,upper=numbers
table=(work/'source/code/native_eabi_m0_refine_table.inc').read_text()
words=list(map(int,re.findall(r'(\d+)U',re.search(r'refine_atan_half_pi\[3\]=\{(.*?)\};',table)[1])))
half_pi=sum(v<<(32*j) for j,v in enumerate(words));one=0x3ff0000000000000;sign=1<<63
rng=random.Random(0x164A51C);distances=set(range(1,65537))
for k in range(1,33):
    distances.update(n for n in range(max(1,(1<<k)-64),(1<<k)+65))
    distances.update((1<<k)|rng.getrandbits(k) for _ in range(256))
distances=sorted(distances);scale_ptr=SP-8192;exponent_ptr=SP-8196
pending=struct.pack('<7I',17,3,0,0,5,2,3)
digest=hashlib.sha256();checked=tight=wide=dirty=intervals=public=0
exponents={};fallbacks={'asin':0,'acos':0};hooks=[]
for op in fallbacks:
    address=m.elf.symbols['mk61_m0_cr_'+op]&~1
    def entered(_uc,_address,_size,_data,operation=op):fallbacks[operation]+=1
    hooks.append(m.uc.hook_add(UC_HOOK_CODE,entered,begin=address,end=address))

def directed(name,x,center=None,radius=None):
    global intervals
    lib.mpfr_set_d(C.byref(arg),real(x),0)
    function=getattr(lib,'mpfr_'+name)
    function(C.byref(lo),C.byref(arg),3);function(C.byref(hi),C.byref(arg),2)
    a=bits(lib.mpfr_get_d(C.byref(lo),0));b=bits(lib.mpfr_get_d(C.byref(hi),0));assert a==b
    if center is not None:
        lib.mpfr_mul_2si(C.byref(lo),C.byref(lo),70,3)
        lib.mpfr_mul_2si(C.byref(hi),C.byref(hi),70,2)
        assert lib.mpfr_set_str(C.byref(lower),str(center-radius).encode(),10,0)==0
        assert lib.mpfr_set_str(C.byref(upper),str(center+radius).encode(),10,0)==0
        assert lib.mpfr_cmp(C.byref(lower),C.byref(lo))<=0 and lib.mpfr_cmp(C.byref(hi),C.byref(upper))<=0,(name,hex(x),center,radius)
        intervals+=1
    return a

try:
    for position,n in enumerate(distances):
        x=one-n;X=((x&((1<<52)-1))|(1<<52))<<10
        is_dirty=position%577==0
        if is_dirty:m.uc.mem_write(0xd0000060,pending)
        qroot=m.call('asin_root_estimate',X,scale_ptr)[0]
        scale=struct.unpack('<I',m.uc.mem_read(scale_ptr,4))[0]
        assert 0<=scale<=26 and qroot
        Y=(qroot+(1<<(scale-1)))>>scale if scale else qroot
        assert Y<X>>6
        q=m.call('asin_atan_small',qroot,X,c=(exponent_ptr<<32)|scale)[0]
        exponent=struct.unpack('<i',m.uc.mem_read(exponent_ptr,4))[0];assert q and -26<=exponent<=-6
        shift=-(exponent+7)
        if shift>0:
            retained,tail=divmod(q,1<<shift);half=1<<(shift-1)
            quant=retained+(tail>half or (tail==half and retained&1))
        else:quant=q<<(-shift)
        radius=2 if exponent<=-13 else 128
        tight+=radius==2;wide+=radius==128
        expected_asin=directed('asin',x,half_pi-quant,radius)
        expected_negative_acos=directed('acos',x|sign,2*half_pi-quant,radius)
        expected_acos=directed('acos',x)
        for op,argument,expected in (('asin',x,expected_asin),('asin',x|sign,expected_asin|sign),
                                     ('acos',x,expected_acos),('acos',x|sign,expected_negative_acos)):
            got=m.call('_ZN12compact_math4'+op+'Ed',argument)[0]
            assert got==expected,(op,hex(argument),hex(got),hex(expected))
            digest.update(struct.pack('<QQQ',argument,expected,got));public+=1
        if is_dirty:
            assert bytes(m.uc.mem_read(0xd0000060,len(pending)))==pending
            dirty+=1
        exponents[str(exponent)]=exponents.get(str(exponent),0)+1;checked+=1
        if checked%16384==0:print('checked',checked,'endpoints;',public,'public calls;',tight,'radius2',flush=True)
finally:
    for hook in hooks:m.uc.hook_del(hook)
    for number in numbers:lib.mpfr_clear(C.byref(number))
record=dict(status='PASS_ACTUAL_ENDPOINT_INTERVALS_AND_PUBLIC_RNE',endpoint_inputs=checked,
    radius2_inputs=tight,radius128_inputs=wide,relative_exponents=exponents,
    actual_fixed_point_interval_checks=intervals,public_RNE_calls=public,dirty_SIO_preservation_checks=dirty,
    public_CORE_MATH_fallback_calls=fallbacks,wrong_intervals=0,wrong_rounding=0,result_sha256=digest.hexdigest(),
    elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),mpfr=oracle.version,
    oracle='192-bit directed MPFR asin/acos bounds. Actual helper integers are converted with the exact production RNE shift; the claimed center+-radius must contain both endpoints after exact2^70 scaling. Both directed endpoints also produce one identical binary64 RNE reference. Negative asin uses its exact odd symmetry.',
    scope='Dense65536 closest inputs below1, neighbourhoods of every distance power2 through2^32, random mantissas at every band, both signs and all4 public operation/sign combinations. Reserved helper output slots are not callee stack measurements. Finite compiled tests, not physical timing.',
    ABI='Every actual helper/public call verifies R4-R11,SP,bounded writes.',hardware_accessed=False,production_promoted=False,goal_complete=False)
(work/'endpoint-qualification.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',checked,'endpoint inputs;',intervals,'actual enclosures;',public,'public RNE calls;',dirty,'dirty SIO checks.')
