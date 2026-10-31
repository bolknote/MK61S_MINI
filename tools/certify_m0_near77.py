#!/usr/bin/env python3
"""Certify packed near-one Q77 logs and their existing Q62 reciprocals."""
import argparse,hashlib,json,re,sys
from fractions import Fraction as F
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from generate_m0_log_table import nearest,logarithm

def floor_log(x,precision):
    z=(x-1)/(x+1);power=z;total=F(0)
    for i in range(100):total+=2*power/(2*i+1);power*=z*z
    upper=total+2*power/(201*(1-z*z))
    lo=total*(1<<precision);hi=upper*(1<<precision)
    q=lo.numerator//lo.denominator
    assert q==hi.numerator//hi.denominator
    return q

def rows():
    result=[]
    for i in range(256):
        c=F(8065+i,8192);inverse=nearest(F(1<<62)/c)
        prefix=0x41 if i==0 else 0x40 if i<128 else 0x3f
        assert inverse>>56==prefix
        log=floor_log(c if c>=1 else 1/c,77)
        assert log<1<<71
        assert (log+64)>>7==logarithm(c if c>=1 else 1/c,70)
        result.append(((inverse&((1<<56)-1))|((log>>64)<<56),log&((1<<64)-1)))
    return result

def packed_source(old):
    assert '#if defined(MK61_M0_RP2040_EABI)' not in old
    begin=old.index('static constexpr U log_near_table[256][2]={')
    old_rows=old[begin:]
    packed='static constexpr U log_near_table[256][2]={\n'+''.join('  {UINT64_C('+str(a)+'),UINT64_C('+str(b)+')},\n' for a,b in rows())+'};\n'
    return old[:begin]+'''// RP2040 stores floor(|ln(c)|*2^77) in71 bits. Reciprocal high bytes
// follow exactly from the center index and need no storage.
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
'''+packed+'#else\n'+old_rows+'''#endif
__attribute__((always_inline)) inline U log_near_inverse(unsigned index) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const unsigned prefix=index==0?0x41U:index<128?0x40U:0x3FU;
  return (log_near_table[index][0]&UINT64_C(0x00FFFFFFFFFFFFFF))|(U(prefix)<<56);
#else
  return log_near_table[index][0];
#endif
}
__attribute__((always_inline)) inline U log_near_value70(unsigned index) {
#if defined(MK61_M0_RP2040_EABI) && MK61_M0_RP2040_EABI
  const U low=log_near_table[index][1],high=log_near_table[index][0]>>56;
  return ((low>>7)|(high<<57))+((low>>6)&1U);
#else
  return log_near_table[index][1];
#endif
}
'''

def certificate(root):
    text=(root/'code/native_eabi_m0_log_table.inc').read_text()
    start=text.index('static constexpr U log_near_table[256][2]={');end=text.index('};',start)
    actual=[tuple(map(int,r)) for r in re.findall(r'\{UINT64_C\((\d+)\),UINT64_C\((\d+)\)\}',text[start:end])]
    expected=rows();assert actual==expected
    h=F(1,16130);scale=1<<77;half=F(1,2)
    argument=half
    square=half+F(1,8192)+2*h*argument+argument*argument/scale
    zr_error=square+(1<<17)
    cube=(F(3,2)+F(3,4096)+F(3,2048)+F(1,1<<29)+
          h*square+h*h*argument+square*argument/scale)
    third=cube/3+F(1,3)
    z16_error=square+(1<<33)
    fourth=half+2*h*h*zr_error+zr_error*zr_error/scale
    c16_error=cube+(1<<19)
    fifth=half+h*h*c16_error+h**3*z16_error+c16_error*z16_error/scale
    error=1+argument/(1-h)+square/2+half+third+fourth/4+half+fifth/5+F(2,5)+scale*h**6/(6*(1-h))
    assert error<5
    assert scale*h+argument<1<<64
    assert scale*h*h+square<1<<50
    assert scale*h**3+cube<1<<36
    assert scale*h**5+fifth<256
    hr=(scale*h+argument+(1<<31))//(1<<32)
    zr=(scale*h*h+square+(1<<17))//(1<<18)
    z16=(scale*h*h+square+(1<<33))//(1<<34)
    c16=(scale*h**3+cube+(1<<19))//(1<<20)
    assert hr<1<<32 and zr<1<<32
    assert hr*zr+(1<<26)<1<<64
    assert zr*zr+(1<<40)<1<<64
    assert z16*z16+256<1<<32 and c16*z16+(1<<22)<1<<32
    assert (scale*h**3+cube+8)//16+1<1<<32
    assert 8320*(1<<16)<1<<32
    assert (1<<48)>>36<8065
    assert 16*(3*171-(1<<9))<1<<9
    assert ((1<<15)*int(zr>>16))+(1<<26)<1<<31
    assert ((1<<15)*int(hr>>16))+(1<<26)<1<<31
    tiny=F(1,1<<14)
    assert (tiny-tiny*tiny/2)*scale-5>1<<62
    assert F(scale,63)+5<1<<72
    assert (256+2)*205<1<<32 and (256+2)*(5*205-(1<<10))<1<<10
    files=['native_eabi_m0_ln_near77.inc','native_eabi_m0_log70.inc','native_eabi_m0_log_table.inc','native_eabi_m0_log10.inc']
    return dict(status='PASS_RATIONAL_NEAR77',source_sha256={n:hashlib.sha256((root/'code'/n).read_bytes()).hexdigest() for n in files},
                table_rows=256,table_bytes=4096,table_growth=0,reciprocal_values_exactly_retained=True,old_Q70_log_values_exactly_reconstructed=True,
                argument_error=str(argument),square_error=str(square),cube_error=str(cube),fourth_error=str(fourth),fifth_error=str(fifth),
                total_Q77_error=str(error),total_Q77_error_float=float(error),strict_error_bound=5,midpoint_reject_radius=4,new_static_RAM=0,
                argument=['Four exact radix2^16 divisions form delta*2^28/(8065+index), using numerators below2^30. Rounding once from the exact remainder gives error<=1/2 Q77 unit; interrupted SIO state uses the established safe division wrapper.',
                          'All256 floor Q77 logs are independently enclosed by100 exact rational atanh-series terms. The known reciprocal prefix is verified for every row, and all original Q70 log values are recovered exactly.',
                          'The high-square kernel supplies z. Rounded32-bit heads supply a coarse cube; two signed16-bit products correct the discarded linear terms with total cube error<1.503. The fourth uses a rounded32x32 square, the fifth uses16-bit heads. All truncations, coefficient divisions, table flooring and degree6 remainder are bounded.',
                          'The complete enclosure must lie in a single binary64 rounding cell. Ambiguous cells retain the original independent refinement.'],
                scope='Algebraic/table/width certificate, not a machine-checked C++ or compiler proof; actual ARM tests remain required.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True);p.add_argument('--json',type=Path,required=True)
    a=p.parse_args();r=certificate(a.source_root);a.json.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status=r['status'],error=r['total_Q77_error_float'],table_bytes=r['table_bytes'])))
if __name__=='__main__':main()
