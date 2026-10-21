#!/usr/bin/env python3
"""Certify independent Q94 sin/cos and Q70 tangent Taylor tables for M0."""
from fractions import Fraction as F
from pathlib import Path
from generate_m0_trig_table import interval
from generate_m0_log_table import nearest

ROOT=Path(__file__).resolve().parents[1]


def rounded(lo,hi,precision):
    if lo==hi==0:return 0
    q=nearest((lo+hi)*(1<<(precision-1)))
    assert F(2*q-1,2)<lo*(1<<precision) and hi*(1<<precision)<F(2*q+1,2)
    return q


def main():
    # The preliminary Q62 pass uses coefficients truncated from Q94.
    # Bound its square, cube, short fourth term, and final products.
    h62=F(1,1<<11)
    cube62=F(1751,1000)
    fourth62=(1+cube62*h62+F(1,1<<13))/24+F(1,2)
    sine62=cube62/6+F(1,2)+(1<<62)*h62**5/120
    cosine62=(1+F(1,1<<22))/2+F(1,2)+fourth62+(1<<62)*h62**6/720
    assert 1+sine62+cosine62+F(1,2)+F(1004,1000)+h62+h62*h62/2<7
    # Ordinary sin/cos uses a Q70 base and Q62 coefficients from the
    # Q94 table below. |h| <= 2^-11 + 2^-63: the extra half Q62 unit
    # covers a cell chosen before adding the Q70 argument tail.
    # A Q70 residual truncated to Q62
    # loses <1/4 Q70 square unit. All arithmetic bounds are absolute.
    hmax=F(1,1<<11)+F(1,1<<63)
    square_error=F(1,2)+F(1,1<<14)+F(1,4)
    cube_error=F(5,2)+square_error*hmax+F(1,1<<14)
    zr_error=F(1,2)+square_error/F(1<<18)
    fourth_error=F(1,2)+(2*(1<<30)*zr_error+zr_error**2)/F(1<<34)
    fifth_error=F(1,2)+fourth_error*hmax+F(1,1<<16)
    assert square_error<F(751,1000) and cube_error<F(2501,1000)
    assert fourth_error<F(563,1000) and fifth_error<F(501,1000)
    # round(round(cube/3)/2) is within 2/3 of cube/6. The two
    # short reciprocal divisions implement nearest, with ties upward.
    assert ((1<<38)+119)//120==0x88888889
    assert ((1<<36)+23)//24==0xAAAAAAAB
    assert ((1<<15)+61)*56<(1<<38)
    assert ((1<<26)+13)*8<(1<<36)
    sine_error=cube_error/6+F(2,3)+fifth_error/120+F(1,2)+(1<<70)*hmax**7/5040
    cosine_error=square_error/2+F(1,2)+fourth_error/24+F(1,2)+(1<<70)*hmax**6/720
    # Base truncation <1; both approximate Q62 products contribute <2.5.
    coefficients_error=256*hmax+128*hmax**2+(sine_error+cosine_error)/F(1<<62)
    assert 1+sine_error+cosine_error+5+coefficients_error<12
    # Q95 argument reduction, n<2^20, followed by Q70 RNE.
    assert F(1,32)+F(1,2)<1
    trig=[];tangents=[]
    for j in range(806):
        x=F(j,1024);sl,sh=interval(x,False);cl,ch=interval(x,True)
        trig.append((rounded(sl,sh,94),rounded(cl,ch,94)))
        tl,th=sl/ch,sh/cl
        functions=(lambda t:t,lambda t:1+t*t,lambda t:t*(1+t*t),
                   lambda t:(1+t*t)*(1+3*t*t)/3,
                   lambda t:t*(1+t*t)*(2+3*t*t)/3,
                   lambda t:(1+t*t)*(2+15*t*t+15*t**4)/15)
        t,a,b,c,d,e=[rounded(f(tl),f(th),p) for f,p in zip(functions,(70,55,50,32,23,14))]
        assert t>>64<128 and a<1<<57 and b<1<<52 and c>>32<4
        assert d<1<<25 and e<1<<17
        tangents.append((t&((1<<64)-1),a|((t>>64)<<57),b|((e>>7)<<52)|((c>>32)<<62),c&0xFFFFFFFF,d|((e&127)<<25)))
    # The packed row stores A in Q55 (reconstructed in Q62), B in
    # Q50, C in Q32, D in Q23 and E in Q14. Certify all quantizations
    # and the native 32-bit fifth-order product independently.
    sl,sh=interval(F(787,1000),False);cl,ch=interval(F(787,1000),True)
    assert sh/cl<F(101,100)
    t=F(101,100);a=1+t*t;b=t*a;c=a*(1+3*t*t)/3
    d=t*a*(2+3*t*t)/3;e=a*(2+15*t*t+15*t**4)/15
    assert t*(17+60*t*t+45*t**4)*a/45<6 and a<3
    # The six-MUL Q70 product keeps the complete argument, with error
    # <35/64. Only the exact z=2^48 endpoint uses a rounded shift.
    assert (1<<70)*hmax*hmax+square_error<(1<<48)+1
    tangent_cube_error=F(35,64)+square_error*hmax
    assert (1<<70)*hmax**3+tangent_cube_error<1<<48
    assert ((1<<48)+(1<<17))>>18==1<<30
    # The tangent fourth-power kernel omits low^2 and the fraction of
    # high*low/2^15. Their sum in the high word is in [0,2), so bias3
    # followed by >>2 has error <=3/4, by its four residue classes.
    tangent_fourth_error=F(3,4)+(2*(1<<30)*zr_error+zr_error**2)/F(1<<34)
    tangent_fifth_error=F(1,2)+tangent_fourth_error*hmax+F(1,1<<16)
    assert (1<<14)**2+(((1<<14)*65535)>>15)+3<1<<32
    assert tangent_fifth_error<F(501,1000)
    def tangent_error(h):
        linear=F(13,2)+16384*h
        second=square_error*b+F(17,32)+F(1,1<<22)+(1<<19)*h**2
        third=tangent_cube_error*c+F(1,2)+(1<<37)*h**3
        fourth=tangent_fourth_error*d+F(1,2)+(1<<46)*h**4
        fifth=tangent_fifth_error*e+F(1,2)+(1<<55)*h**5
        return F(1,2)+linear+second+third+fourth+fifth+6*(1<<70)*h**6
    assert tangent_error(hmax)<143
    assert tangent_error(F(1,1<<12))<25
    assert (1<<70)*hmax**5+tangent_fifth_error<32769
    emax=(e*(1<<14)+F(1,2)).__ceil__()
    assert emax<1<<17
    assert 32769*emax+(1<<13)<1<<32
    # A rare local refinement adds the sixth term. Its coefficient uses
    # a Q8 tangent and three Q8 Horner stages, with exact /11520 rounding.
    et=F(1,512)+F(1,1<<71)
    eu=2*t*et+et*et+F(1,512);umax=t*t+eu
    assert (17+77*umax+105*umax**2+45*umax**3)/45<6
    assert (t+et)*(77+210*umax+135*umax**2)/45<10
    ec=6*et+10*eu+(t+et)*(umax+1)/(45*512)+F(1,512)
    assert ec<F(75,1000)
    t8max=int(256*t+F(1,2)+F(1,1<<63))
    u8max=(t8max*t8max+128)>>8
    p1max=105*256+45*u8max
    assert p1max*u8max+128<1<<32
    p2max=77*256+((p1max*u8max+128)>>8)
    assert p2max*u8max+128<1<<32
    p3max=17*256+((p2max*u8max+128)>>8)
    assert p3max*t8max+5760<1<<32
    c8max=(p3max*t8max+5760)//11520
    assert c8max*256+2048<1<<32
    # g=|h|*2048 is rounded to Q8, then squared/cubed/squared.
    gmax=2048*hmax;eg=F(1,512)
    assert int(256*gmax+F(1,2))==256
    eg2=2*gmax*eg+eg*eg+F(1,512)
    eg3=gmax*eg2+gmax*gmax*eg+eg2*eg+F(1,512)
    eg6=2*gmax**3*eg3+eg3*eg3+F(1,512)
    sixth=16*(6*eg6+ec*(gmax**6+eg6))+F(1,2)
    assert sixth<4
    assert (1+t*t)*(17+231*t*t+525*t**4+315*t**6)/315<8
    fine=tangent_error(hmax)-6*(1<<70)*hmax**6+sixth+8*(1<<70)*hmax**7
    assert fine<51
    # If the rounded square is zero, its true value is <0.751 Q70.
    # Enclose all nonlinear terms with tan''/2 < t*(1+t*t).
    assert F(16384,1<<35)<F(1,1000)
    assert F(1,2)+F(13,2)+F(1,1000)+F(751,1000)*t*(1+t*t)<9
    assert 1+t*t<3
    coefficients=[[nearest(F(1<<94,d)) for d in denominators]
                  for denominators in ((6,120,5040,362880),(2,24,720,40320))]
    target=ROOT/'code/native_eabi_m0_trig_checked_table.inc'
    target.write_text('// Generated by tools/generate_m0_trig_checked_table.py; rational certificates.\n'
        'static constexpr uint32_t trig94_table[806][6]={\n'+
        ''.join('  {'+','.join(str((q>>(32*k))&0xFFFFFFFF)+'U' for q in row for k in range(3))+'},\n' for row in trig)+'};\n'
        '// first packs A in Q55 and the Q70 value high limb; second packs B/C/E high.\n'
        '// polynomial packs D in Q23 (25 bits) and E low (7 of its 17 Q14 bits).\n'
        'struct TrigTanRow {U value,first,second;uint32_t third,polynomial;};\n'
        'static_assert(sizeof(TrigTanRow)==32,"Compact tangent row layout");\n'
        'static constexpr TrigTanRow trig_tan_table[806]={\n'+
        ''.join('  {'+','.join('UINT64_C('+str(q)+')' if k<3 else str(q)+'U' for k,q in enumerate(row))+'},\n' for row in tangents)+'};\n'
        'static constexpr uint32_t trig94_coefficients[2][4][3]={\n'+
        ''.join('  {'+','.join('{'+','.join(str((q>>(32*k))&0xFFFFFFFF)+'U' for k in range(3))+'}' for q in row)+'},\n' for row in coefficients)+'};\n')
    return {'tangent_error_q70':str(tangent_error(hmax)),
            'tangent_half_cell_error_q70':str(tangent_error(F(1,1<<12))),
            'sixth_term_error_q70':str(sixth),'refined_tangent_error_q70':str(fine)}


if __name__=='__main__':main()
