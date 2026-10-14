#!/usr/bin/env python3
"""All physical D6/A7 sources with a hidden U marker and no visible marker.

This classifies the ROM suffix, not which source a requested key selects.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()

for index in range(15):
    start=(index+7)%15;seq=[0xD6,0xA7]
    while (start+len(seq))%15 not in (0,7):seq.append(0xE5)
    found=(start+len(seq))%15
    seq.extend([0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9])
    pages=[State('clone_window_%d_%d'%(index,i)).m for i in range(len(seq)+1)]
    a=State('clone_window_'+str(index));a.m=pages[0];p=base(a,0xD6)
    p.add(stack(a)[0]==0xA7,stack(a)[1]==0xAC)
    for i,ip in enumerate(seq):
        if ip==0xE5:p.add(pages[i][22]==15 if (start+i)%15 in (0,7) else pages[i][22]!=15)
    b=a;carry=[pages[0][3*j] for j in range(12)];targets=[]
    for i,ip in enumerate(seq):
        label='%X/%02X/%s'%(index,ip,slots[(start+i)%15])
        prove(p,address(b)==ip,label+' forced address')
        out=[];b=ex(b,ip,*keys(label),serial_inputs=pages[i+1],emitted_outputs=out)
        if ip in (0xE7,0xA8):
            targets.append(slots[(start+i)%15])
            prove(p,And(*[out[1+3*j]==carry[j] for j in range(12)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
                  label+' exactly 12 numeric writes')
            carry=[pages[i][1+3*j] for j in range(12)]
        else:prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),label+' ring held')
    assert targets==(['X','Y','Z','T'] if index<=6 or index==14 else ['Q','P7','P8','P9'])
    prove(p,And(address(b)==0xAC,b.s1==0),'finite AC return')
    print('PASS: physical M1 %X(%s) -> marker %s -> %s'%(index,slots[start],slots[found],'/'.join(targets)),flush=True)
print('LIMIT: no key-to-source mapping or safe formatter return is inferred from this exhaustive physical-position classification.',flush=True)
