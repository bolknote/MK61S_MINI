"""Isolated-round verification: retain significant digits and actual ROM sign(0)."""
import math
from decimal import Decimal
import full_isa_math
import ar_spec
from ha_protocol import canonical

ORIGINAL_VALUE=full_isa_math.value

def value(expr,values,angle):
    if isinstance(expr,list)and expr[0]=='sign':
        x=value(expr[1],values,angle);return -1 if x<0 else 1 if x>0 else 0
    return ORIGINAL_VALUE(expr,values,angle)

def close(a,b):
    if a is None:return False
    a,b=float(a),float(b)
    return math.isfinite(a)and abs(a-b)<=(1e-12 if b==0 else abs(b)*2e-6)

def install():
    # Only this process changes; all historical source files and results remain frozen.
    full_isa_math.value=value;ar_spec.value=value;ar_spec.close=close

def normal(expr):
    if isinstance(expr,str):return expr
    if isinstance(expr,dict):return {'pi':True}if'pi'in expr else{'constant':canonical(expr['constant'])}
    op,*args=expr;args=[normal(a)for a in args]
    if op=='neg'and isinstance(args[0],dict)and'constant'in args[0]:return {'constant':canonical(-Decimal(args[0]['constant']))}
    if op=='reciprocal':op='/';args=[{'constant':'1'},args[0]]
    if op=='square':op='pow';args=[args[0],{'constant':'2'}]
    if op=='pow10':op='pow';args=[{'constant':'10'},args[0]]
    if op=='*'and args[0]==args[1]:op='pow';args=[args[0],{'constant':'2'}]
    if op in ['+','*']:
        import json
        args.sort(key=lambda a:json.dumps(a,sort_keys=True))
    return [op,*args]

def equal_spec(a,b):
    return (a['angle']==b['angle']and normal(a['X'])==normal(b['X'])and
        {r:normal(x)for r,x in a['writes'].items()}=={r:normal(x)for r,x in b['writes'].items()})
