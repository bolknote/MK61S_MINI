"""Rational error bounds for the RP2040 shortcuts around Classic's pow."""
import math
import re
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT/'code/compact_math.cpp').read_text().split('namespace power {',1)[1]
u = F(1, 2**53)
tiny = F(1, 2**1074)


def rounding(magnitude):
    return magnitude*u + tiny


def constant(name):
    return F(float(re.search(r'\b'+name+r'\s*=\s*([-+.0-9e]+)', source)[1]))


def log_series(s):
    terms = 96
    lower = 2*sum(s**(2*i+1)/(2*i+1) for i in range(terms))
    return lower, lower+2*s**(2*terms+1)/((2*terms+1)*(1-s*s))


def certify():
    ln2, ln2_upper = log_series(F(1,3))
    ln15, ln15_upper = log_series(F(1,5))
    cp, ch, cl = (constant(k) for k in ('cp','cp_h','cp_l'))
    dp_h = F(float(re.search(r'dp_h\[\]\s*=\s*\{\s*0.0,\s*([.0-9e+-]+)',source)[1]))
    dp_l = F(float(re.search(r'dp_l\[\]\s*=\s*\{\s*0.0,\s*([.0-9e+-]+)',source)[1]))
    for l in (ln2,ln2_upper):
        assert abs(ch+cl-2/(3*l)) < F(1,2**78) and abs(cp-2/(3*l)) < u
        assert max(abs(dp_h+dp_l-v/l) for v in (ln15,ln15_upper)) < F(1,2**77)
        assert abs(constant('lg2_h')+constant('lg2_l')-l) < F(1,2**80)
        assert abs(constant('lg2')-l) < u
        assert round(l*2**62) == 0x2c5c85fdf473de6b
    assert ch.numerator.bit_length()+21 <= 53
    assert constant('lg2_h').numerator.bit_length()+21 <= 53
    assert (dp_h*2**26).denominator == 1

    # ax and bp are integer multiples of 2^-53. Check the two extreme low
    # words of every possible normalized high word. D, t_l and s are monotone
    # within each interval. t_h-bp is exact on the high-word grid and the
    # subtraction from ax is exact by Sterbenz.
    def scaled(high, low=0):
        mantissa = (1<<52) + ((high & 0xfffff)<<32) + low
        return mantissa << ((high>>20)-1022)
    unit = 1<<53
    for j in range(1<<20):
        k = int(0x3988e < j < 0xbb67a)
        ix = (0x3ff00000 | j) - (int(j>=0xbb67a)<<20)
        b = unit+k*(unit//2)
        th = scaled(((ix>>1)|0x20000000)+0x80000+(k<<18))
        for x in (scaled(ix), scaled(ix,0xffffffff)):
            assert 7*unit <= 4*(x+b) <= 16*unit
            assert 500*abs(x-b) < 51*(x+b)
            assert abs(x-(th-b)) <= unit>>19
            assert b <= 2*x and x <= 2*b and th-b <= 2*x and x <= 2*(th-b)
    s = F(51,500)
    # Ideal log polynomial error. Bound signed coefficient differences on
    # whole intervals of z=s^2, with the analytic atanh tail beyond degree 33.
    coeff = [constant('L'+str(i+1)) for i in range(6)]
    diff = [(coeff[i] if i<6 else 0)-F(3,5+2*i) for i in range(15)]
    poly_error = F(0)
    for i in range(256):
        left, right = i*s*s/256, (i+1)*s*s/256
        lo = hi = diff[-1]
        for c in reversed(diff[:-1]):
            lo, hi = c+min(left*lo,right*lo), c+max(left*hi,right*hi)
        poly_error = max(poly_error, max(abs(lo),abs(hi))*s**5)
    poly_error += 3*s**35/(35*(1-s*s))

    # s_h+s_l approximates (ax-bp)/D. The high product s_h*t_h is exact.
    # The error model allows rounding even on exact cancellations.
    ess = 4*u*s
    ds = s*F(1,2**20) + 2*ess  # |s_h-s|
    sh = s+ds
    dt = F(1,2**19)             # |D-t_h|
    e1 = rounding(4*ds+sh*dt)   # u-s_h*t_h
    e2 = rounding(sh*dt)        # s_h*t_l
    e3 = e1+e2+rounding(4*ds+e1+e2)
    esl = e3 + 3*u*ds + rounding(ds+e3+3*u*ds)
    sl = ds+esl

    # R=(ss^2)^2 * Horner(ss^2) plus s_l*(s_h+ss).
    z = F(11,1000)
    ez = ess*(2*s+ess)+rounding((s+ess)**2)
    assert s*s+ez < z and max(coeff) < 1-z
    # |H| <= 1, |H'| <= 1/(1-z)^2. Bound rounding in all five stages.
    eh = (rounding(z)+rounding(1+rounding(z)))/(1-z)
    er = ez*(2*z+z*z/(1-z)**2) + rounding(z*z)*(1+eh) + z*z*eh + rounding(2*z*z)
    ec = esl*(2*sh+ess)+sl*ess+sl*rounding(2*sh+ess)+rounding(3*sh*sl)
    rr = F(1,7000)
    assert z*z*(1+eh)+er+3*sh*sl < rr
    er += ec+rounding(rr)

    # t_h+t_l = 3+s^2+R. t_h differs from its unsplit sum by <2^-18.
    tgap = F(1,2**18)
    assert F(1,2**19)+2*rounding(4) < tgap
    et = er+rounding(rr+tgap)+rounding(2*tgap)
    # u=s_h*t_h exact; v=s_l*t_h+t_l*ss. Recover p_h+p_l.
    ev = 4*esl+2*tgap*ess+rounding(4*sl)+rounding(2*tgap*sh)+rounding(4*sl+2*tgap*sh+u)
    pv = ev+s*et+2*rounding(F(1,2**18))
    # cp_h*p_h is exact. The low products and dp_l have magnitude <2^-18.
    ec = pv+F(1,2**78)+u*F(1,2**19)+4*rounding(F(1,2**18))
    # |n| <= 4. Unless n=dp_h=0, |t1| > 1/16, since the centered log
    # has magnitude <0.31. t1-n and (t1-n)-dp_h are exact on a 2^-26 grid.
    # In either case the last difference and t2 are bounded by 2^-16.
    log_error = ec+poly_error+F(1,2**77)+2*rounding(F(1,2**16))
    assert log_error < F(1,2**60)

    # y1*t1 is exact. The remaining two products and their sum are
    # each below 2^-15 * |y|. This includes rounding y-y1 (Sterbenz).
    log_product = log_error+4*u*F(1,2**15)+tiny*2**16
    assert log_product*2**64 < 3
    # |log2 x| <= 4. Splitting y and the log at the high word bounds
    # |p_l| even at |y| just below 32. For |p_h+p_l| <= 129 the integer
    # reduction leaves a remainder <= 1/2 + 2^-20 (the high-word cutoff
    # at 0.5). A nonzero n subtracts exactly from the <=42-bit p_h.
    assert (1+4*u)*((4+F(1,2**16))*F(1,2**20)+F(1,2**16)) < F(1,2**15)
    assert F(1,2)+F(1,2**20)+F(1,1024) < F(5,8)
    assert (F(1,2)+F(1,2**20))*ln2_upper+4*F(1,2**62) < F(2,5)

    # After subtracting the integer n, |p_h| < 5/8, |p_l| < 1/1024.
    # t, the high part of RN(p_h+p_l), misses that real sum by <2^-19.
    # t*lg2_h is exact. Bound the other three products/sums and FastTwoSum.
    gap = F(1,2**19)
    ed = rounding(F(1,1024)+gap)
    en = ed + 5*rounding(2*gap) + u*gap + F(1,2**80)
    eq = (en+2*rounding(3*gap))*2**62+1   # two Q62 conversions
    assert eq < 3
    # Replacing both parts by Q62 then multiplying by rounded ln(2)
    # contributes at most another 2 Q62 units.
    assert ln2_upper + F(1,2)*(1+F(5,8)+F(1,1024))+tiny < 2
    radius = F(2,5)
    # Exact factorial coefficients rounded to Q62 plus 15 rounded products.
    # Both error series contract at each step by at most radius.
    coeff_text = (ROOT/'code/compact_math_tables.hpp').read_text().split('exponential_coefficients[] = {')[1].split('}')[0]
    assert list(map(int,re.findall(r'(\d+)LL',coeff_text))) == [round(F(2**62,math.factorial(i))) for i in range(16)]
    horner = 1/(1-radius) + 2**62*radius**16/math.factorial(16)/(1-radius/17)
    assert horner < 2
    # The positive polynomial is > 1-radius-2/2^62. Convert its absolute
    # error to a logarithmic perturbation via the mean value theorem for ln.
    log_horner = 4*horner/(1-radius-F(2,2**62))
    assert 4*eq+log_horner < 20
    assert 4*(eq+2)+log_horner < 28
    # On the tiny-y shortcut, |n| <= 1074 and the bounded centered terms
    # give |log2(ax)| < 1076. Even a loose split-product bound of 1080
    # keeps the rounded polynomial inside the narrower half of 1's cell.
    assert 2*(1080*ln2_upper*F(1,2**65)+4*F(1,2**62)) < F(1,2**54)
    print('PASS: <3*|y| Q64 units for the Classic log product; 20 and 28 Q64 units for reduced exp.')


if __name__ == '__main__':
    certify()
