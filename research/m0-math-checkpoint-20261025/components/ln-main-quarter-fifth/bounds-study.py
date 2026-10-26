"""Exact one-sided error propagation for unchanged Q70 main-ln arithmetic."""
from pathlib import Path
from fractions import Fraction as F
import json

W=Path(__file__).resolve().parent
S=1<<70
h=F(1,2048)
square=1+F(1,1<<16)
cube=F(35,64)+h*square
fourth_lower=1+63*h+(S*h**3+cube)/(1<<43)+h*cube
fourth_upper=h*cube
fifth_lower=1+h*fourth_lower+(S*h**4+fourth_upper)/(1<<43)
fifth_upper=h*fourth_upper
third=cube/3+F(1,3)
remainder=S*h**6/(6*(1-h))
argument=F(106497,16384)
nonlinear=argument*h/(1-h)
neg_lower=F(1,2)+1+third+fourth_upper/4+F(1,2)+fifth_upper/5+F(2,5)
neg_upper=F(1,2)+square/2+third+fourth_lower/4+F(1,4)+fifth_lower/5+F(2,5)+remainder
pos_lower=F(1,2)+1+third+fourth_upper/4+F(1,2)+fifth_lower/5+F(2,5)
pos_upper=F(1,2)+square/2+third+fourth_lower/4+F(1,4)+fifth_upper/5+F(2,5)+remainder
assert neg_lower+1/(1-h)<4 and neg_upper<6
assert pos_lower<4 and pos_upper+1/(1-h)<7
assert neg_lower+nonlinear<3 and neg_upper+nonlinear<6
assert pos_lower+nonlinear<4 and pos_upper+nonlinear<6
# All actual fifth values fit this interval; the multiply implements
# nearest /5 exactly, with error in {-2,-1,0,1,2}/5.
assert S*h**5+fifth_upper < (1<<16)
for v in range(1<<16):
    assert ((v+2)*52429)>>18 == (v+2)//5
    assert (v+2)*52429 < (1<<32)
# Positive outer endpoints in the first32 cells have a positive Taylor
# omission, supplying a tighter lower bound without coefficient changes.
minimum=F(255,256*2111)
endpoint_remainder=S*minimum**6/(6*(1+h))
assert pos_lower-endpoint_remainder<1
assert pos_lower+nonlinear-endpoint_remainder<1
names=('h','square','cube','fourth_lower','fourth_upper','fifth_lower','fifth_upper',
       'remainder','nonlinear','neg_lower','neg_upper','pos_lower','pos_upper','endpoint_remainder')
out=dict(status='EXPLORATORY_EXACT_ASYMMETRIC_Q70_BOUNDS_NOT_RUNTIME_QUALIFICATION',
    terms={n:dict(exact=str(globals()[n]),approx=float(globals()[n])) for n in names},
    exact_radii=dict(negative_below=4,negative_above=6,positive_below=4,positive_above=7),
    raw_residual_radii=dict(negative_below=3,negative_above=6,positive_below=4,positive_above=6),
    positive_endpoint_lower_radius=1,endpoint_domain='k=0, index<=31, offset_high10>=1022',
    fifth_divide_finite_cases=65536,new_tables=False,hardware_accessed=False)
(W/'bounds-study.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
