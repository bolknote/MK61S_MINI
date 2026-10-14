#!/usr/bin/env python3
"""Local alternative EE return, and the two ordinary caller contracts.

No native state is changed. The EE/top46 gadget is conditional until a
separate reset-reachability audit supplies or excludes its entry.
"""
import runpy
from pathlib import Path
from z3 import And, If, BitVecVal, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);result=p.check()
    assert result==unsat,(label,p.model() if result==sat else result)
    p.pop();print('PASS:',label,flush=True)

a=State('raw_ee');p=base(a,0xEE);out=[];b=ex(a,0xEE,*keys('raw_ee_keys'),emitted_outputs=out)
prove(p,And(address(b)==stack(a)[0],*[b.r[3*j]==a.m[1+3*j] for j in range(12)],
            *[x==y for x,y in zip(out,a.m)]),
      'EE reads all twelve arbitrary numeric tetras, writes none, and returns to the old stack top')

for ip,ret,selector in ((0xE2,0xE3,13),(0xFF,0xF0,14)):
    a=State('caller_%02X'%ip);p=base(a,ip);out=[];b=ex(a,ip,*keys('caller_keys_%02X'%ip),emitted_outputs=out)
    prove(p,And(address(b)==0xE5,b.s1==selector,*[x==y for x,y in zip(stack(b),[ret]+stack(a)[:2])],
                *[x==y for x,y in zip(out,a.m)]),
          '%02X fixes selector %X and return %02X, regardless of incoming mode flags'%(ip,selector,ret))
    # A single scan step supplies an inductive invariant for arbitrarily
    # many marker waits. No finite waiting bound is assumed.
    a=State('scan_%02X'%ip);p=base(a,0xE5);out=[];b=ex(a,0xE5,*keys('scan_keys_%02X'%ip),emitted_outputs=out)
    prove(p,And(address(b)==If(a.m[22]==15,BitVecVal(0xE6,8),BitVecVal(0xE5,8)),b.s1==a.s1,
                *[x==y for x,y in zip(stack(b),stack(a))],*[x==y for x,y in zip(out,a.m)]),
          'caller %02X: every E5 wait holds the selector and return tag'%(ip))
    a=State('select_%02X'%ip);p=base(a,0xE6);p.add(a.s1==selector);b=ex(a,0xE6,*keys('select_keys_%02X'%ip))
    prove(p,And(address(b)==(0xED if selector==13 else 0xEE),
                *[x==y for x,y in zip(stack(b),stack(a))]),
          'caller %02X selects %s after the marker'%(ip,'ED then EE at marker+3' if selector==13 else 'EE at marker+2'))

a=State('constructor46');p=base(a,0x45);b=ex(a,0x45,*keys('constructor46_keys'))
prove(p,And(address(b)==0x8B,*[x==y for x,y in zip(stack(b),[0x46]+stack(a)[:2])]),
      '45 really constructs return 46 and enters 8B; this alone does not establish EE/top46')

names=['X','Y','Z','T','U','V','W'];pages=[State('gadget46_'+n).m for n in names]
a=State('gadget46');a.m=pages[0];p=base(a,0xEE);p.add(stack(a)[0]==0x46,pages[2][22]==15)
source=[pages[0][1+3*j] for j in range(12)];b=a
for i,ip in enumerate((0xEE,0x46,0xE5,0xE6,0xE8,0xE7)):
    label='gadget %02X(%s)'%(ip,names[i]);prove(p,address(b)==ip,label+' forced')
    out=[];b=ex(b,ip,*keys(label),serial_inputs=pages[i+1],emitted_outputs=out)
    if ip==0xE7:
        prove(p,And(*[out[1+3*j]==source[j] for j in range(12)],
                    *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37],
                    *[b.r[3*j]==pages[i][1+3*j] for j in range(12)],address(b)==0x47),
              label+' only V receives exact arbitrary p, including unchanged service/program/M1 tetras; return 47')
    else:prove(p,And(*[x==y for x,y in zip(out,pages[i])]),label+' no ring write')
print('LIMIT: alternative return 46 is a local gadget contract, not a keyboard protocol; consult k1-formatter-entry-audit.py for reset reachability.',flush=True)
