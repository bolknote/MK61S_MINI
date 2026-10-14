"""Independent mpmath oracle; development dependency, absent from test runners."""
import math
import random
import struct
from pathlib import Path
import mpmath as mp

ROOT=Path(__file__).resolve().parents[1]
RANDOM=random.Random(0xFD611B)
def bits(x): return struct.unpack('<Q',struct.pack('<d',x))[0]
def value(x): return struct.unpack('<d',struct.pack('<Q',x))[0]
def finite():
    b=RANDOM.getrandbits(64)
    if b&0x7FF0000000000000==0x7FF0000000000000: b ^= 1<<52
    return value(b)
def neighbors(x):
    return (x,math.nextafter(x,-math.inf),math.nextafter(x,math.inf))
def unary(name,x):
    function={'ln':mp.log,'log10':mp.log10}.get(name,getattr(mp,name,None))
    return float(function(mp.mpf(x)))
def power(x,y):
    p=mp.mpf(y)*mp.log(mp.mpf(x))
    if p>800: return math.inf
    if p< -800: return 0.0
    return float(mp.exp(p))

records=[]
def add(name,x,y=0.0):
    if name in ('ln','log10','sqrt') and x<=0: return
    if name in ('asin','acos') and abs(x)>1: return
    if not math.isfinite(x) or not math.isfinite(y): return
    expected=[]
    for precision in (400,450):
        with mp.workdps(precision):
            expected.append(power(x,y) if name=='pow' else unary(name,x))
    assert bits(expected[0])==bits(expected[1]),(name,x,y,expected)
    records.append((name,bits(x),bits(y),bits(expected[0])))

names=('sin','cos','tan','asin','acos','atan','ln','log10','exp','sqrt')
for name in names:
    for x in (1.0,0.5,0.25,-0.5,-1.0):
        for near in neighbors(x): add(name,near)
    for x in (value(1),value(0x000FFFFFFFFFFFFF),value(0x0010000000000000),
              value(0x7FEFFFFFFFFFFFFF)):
        add(name,x);add(name,-x)
    for exponent in (-1074,-1022,-1000,-53,-26,-1,0,1,20,100,500,900,1023):
        x=math.ldexp(1.0,exponent)
        for near in neighbors(x): add(name,near)
    for _ in range(80):
        x=finite()
        if name in ('ln','log10','sqrt'): x=abs(x)
        elif name in ('asin','acos'): x=RANDOM.random()*2-1
        elif name=='exp': x=RANDOM.random()*1500-760
        add(name,x)
    if name in ('sin','cos','tan'):
        for e in (0,1,2,10,18,20,40,100,500,900,1022):
            x=math.ldexp(math.pi/2,e)
            for near in neighbors(x): add(name,near);add(name,-near)
    if name=='exp':
        for x in (709.782712893384,-745.1332191019411):
            for near in neighbors(x): add(name,near)
for _ in range(180):
    x=abs(finite())
    if x==0: continue
    add('pow',x,RANDOM.random()*16-8)
    near_one=value(0x3FF0000000000000+RANDOM.randrange(-0x100000000,0x100000001))
    add('pow',near_one,math.ldexp(RANDOM.random()*2-1,RANDOM.randrange(65)))
for e in (-1074,-1022,-500,-53,-1,0,1,53,500,1023):
    x=math.ldexp(1.0,e)
    for y in (0.5,1.5,-1.5,2.0,3.0,4.0,-3.0,1/3):
        add('pow',x,y)
records=list(dict.fromkeys(records))
path=ROOT/'tests/fixtures/compact_math_binary64.tsv'
path.parent.mkdir(parents=True,exist_ok=True)
text='# Independent mpmath 1.3.0 reference, exact binary64 inputs, 400/450 decimal digits agree.\n'
text+='# Seed 0xFD611B. Columns: operation input1_bits input2_bits rounded_result_bits.\n'
text+=''.join(f'{name}\t{x:016X}\t{y:016X}\t{result:016X}\n' for name,x,y,result in records)
path.write_text(text)
print('Independent binary64 vectors:',len(records),'both oracle precisions agree')
