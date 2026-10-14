#!/usr/bin/env python3
"""P9-positioned M1 load followed by a four-word Ms push.

The native test supplies physical placement. Every numeric tetra, key signal,
and unrelated input remains arbitrary within this connected ROM suffix.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
    print('PASS:',label,flush=True)

a=State('p9_push_decode');p=base(a,0xAB);p.add(a.r[32]==9,a.r[35]==6);b=a
for i,ip in enumerate([0xAB,0xAD,0xA6]):
    prove(p,address(b)==ip,'recall 69 reaches %02X independently of the previous M2 read'%ip)
    b=ex(b,ip,*keys('p9_push_decode_keys_'+str(i)))
prove(p,And(address(b)==1,b.s1==6,stack(b)[0]==0xA7,b.r[35]==9),
      '69 selects full M1 load D6 with register digit 9 and return A7')

names=['control','X1','X','Y','Z','T','U','V','W','Q','P7','P8']
seq=[0xD6,0xA7,0xE5,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
pages=[State('p9_push_page_'+n).m for n in names]
a=State('p9_push_suffix');a.m=pages[0];p=base(a,0xD6)
p.add(stack(a)[0]==0xA7,stack(a)[1]==0xAC,pages[2][22]!=15,pages[3][22]==15)
b=a;source=[pages[0][3*i] for i in range(12)]
for i,ip in enumerate(seq):
    prove(p,address(b)==ip,'P9 suffix executes %02X at %s'%(ip,names[i]))
    out=[];b=ex(b,ip,*keys('p9_push_suffix_keys_'+str(i)),serial_inputs=pages[i+1],emitted_outputs=out)
    if 6<=i<=9:
        incoming=source if i==6 else [pages[i-1][1+3*j] for j in range(12)]
        prove(p,And(*[out[1+3*j]==incoming[j] for j in range(12)],
                    *[b.r[3*j]==pages[i][1+3*j] for j in range(12)],
                    *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
              'exact full-word swap at '+names[i]+'; other lanes/service unchanged')
    else:
        prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),'no ring writes at '+names[i])
    if i<6:
        prove(p,And(*[b.r[3*j]==source[j] for j in range(12)]),
              'all twelve P9 tetras survive through %02X'%ip)
prove(p,And(address(b)==0xAC,b.s1==0),'finite Ms push returns to AC, not another swap block')
print('NOT full K1: P9 is copied into U and old Q is discarded by the surrounding operation.',flush=True)
