"""Pure exact bounds; importing this module never creates artifacts."""
from fractions import Fraction as F

S=1<<70
ARGUMENT=F(106497,16384)

def enclosures(denominator_minimum):
    assert denominator_minimum in (2049,2081,3585)
    h=F(1,denominator_minimum-1)
    assert F(1,denominator_minimum)+ARGUMENT/S<h
    square=1+F(1,1<<16)
    cube=F(35,64)+h*square
    fourth_lower=1+63*h+(S*h**3+cube)/(1<<43)+h*cube
    fourth_upper=h*cube
    fifth_lower=1+h*fourth_lower+(S*h**4+fourth_upper)/(1<<43)
    fifth_upper=h*fourth_upper
    nonlinear=ARGUMENT*h/(1-h)
    remainder=S*h**6/(6*(1-h))
    # Known coefficient bias r4/4 +/-r5/5 is excluded. The square
    # rounding still ranges[-1/2,0], and third rounding[-1/3,+1/3].
    positive_lower=(nonlinear+F(1,2)+1+cube/3+F(1,3)+
                    fourth_upper/4+fifth_lower/5)
    positive_upper=(nonlinear+F(1,2)+square/2+cube/3+F(1,3)+
                    fourth_lower/4+fifth_upper/5+remainder)
    negative_lower=(nonlinear+F(1,2)+1+cube/3+F(1,3)+
                    fourth_upper/4+fifth_upper/5)
    negative_upper=(nonlinear+F(1,2)+square/2+cube/3+F(1,3)+
                    fourth_lower/4+fifth_lower/5+remainder)
    assert positive_lower<F(9,4) and negative_lower<F(17,8)
    if denominator_minimum==2049:
        assert positive_upper<F(9,2) and negative_upper<F(19,4)
    elif denominator_minimum==2081:
        assert positive_upper<F(17,4) and negative_upper<F(9,2)
    else:
        assert positive_upper<2 and negative_upper<F(17,8)
    assert S*h**5+fifth_upper<65536
    return locals()

def radii40(den,negative):
    lower=85 if negative else 90
    upper=(85 if negative else 80) if den>=3585 else (
          (180 if negative else 170) if den>=2081 else (190 if negative else 180))
    return lower,upper

def coefficient_bias20(fourth,fifth,negative):
    r4=((fourth+2)&3)-2
    r5=fifth-5*(((fifth+2)*52429)>>18)
    return 5*r4+(4*r5 if negative else -4*r5)

def gate(distance,above,sign,n,den,oriented,negative,fourth,fifth):
    lower,upper=radii40(den,negative)
    bias=coefficient_bias20(fourth,fifth,negative)
    if sign:
        lower,upper=upper,lower
        bias=-bias
    limit=upper if above else lower+20*n
    adjustment=2*bias*den-40*oriented
    return (40*distance-limit)*den+(-adjustment if above else adjustment)>=0

def interval(sign,n,den,residue,negative,fourth,fifth):
    minimum=3585 if den>=3585 else 2081 if den>=2081 else 2049
    bounds=enclosures(minimum)
    prefix='negative' if negative else 'positive'
    lower,upper=-bounds[prefix+'_lower'],bounds[prefix+'_upper']
    bias=F(coefficient_bias20(fourth,fifth,negative),20)
    oriented=-residue if negative!=sign else residue
    linear=-F(oriented,den)
    if sign:
        lower,upper=-upper,-lower
        bias=-bias
    # ln2 error is in(-1/2,0), including n=0 exactly.
    return lower+bias+linear-F(n,2),upper+bias+linear
