#!/usr/bin/env python3
"""Conditional cleanup shared by successful W reads and harmless zero misses.

D6 reloads ordinary P0, then its address-dependent scan passes the false T
and starts the visible push at X. It does not use a false U control word
as the address base. Native tests must establish the D6 physical entry.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
seq=[0xD6,0xA7]+[0xE5]*7+[0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
names=[slots[(7+i)%15] for i in range(len(seq)+1)]
pages={n:State('retry_cleanup_'+n).m for n in slots}
a=State('retry_cleanup');a.m=pages['U'];p=base(a,0xD6)
p.add(byte(a.st[36],a.st[39])==0xA7,byte(a.st[37],a.st[40])==0xAC)
for n in ['W','Q','P7','P8','P9','P10','marker']:
    p.add(pages[n][22]==15 if n=='marker' else pages[n][22]!=15)
for n in ['X','Y','Z']:p.add(*[pages[n][1+3*j]==0 for j in range(12)])
p.add(*[pages['T'][1+3*j]==(15 if j==7 else 0) for j in range(12)])
source=[pages['U'][3*j] for j in range(12)]
def prove(claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim);result=p.check()
    assert result==unsat,(label,p.model() if result==sat else result)
    p.pop()
b=a;carried=source;written={}
for i,ip in enumerate(seq):
    label='%02X(%s)'%(ip,names[i]);prove(address(b)==ip,label+' address')
    out=[];b=ex(b,ip,*keys('retry_cleanup_keys_'+str(i)),
                serial_inputs=pages[names[i+1]],emitted_outputs=out)
    if ip in (0xE7,0xA8):
        prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                  *[out[j]==pages[names[i]][j] for j in range(42) if j%3!=1 or j>=37]),
              label+' exact twelve-tetra swap')
        written[names[i]]=out;carried=[pages[names[i]][1+3*j] for j in range(12)]
    else:prove(And(*[x==y for x,y in zip(out,pages[names[i]])]),label+' no ring writes')
assert list(written)==['X','Y','Z','T']
prove(And(address(b)==0xAC,b.s1==0,*[written['X'][1+3*j]==source[j] for j in range(12)],
          *[written[n][1+3*j]==0 for n in ['Y','Z','T'] for j in range(12)]),
      'P0 copied to X, only extra marker removed, no X1 or stored-bank changes, AC return')
print('PASS 16 connected commands: arbitrary ordinary P0 copied to X; marker T dropped; X1 and all stored banks held.',flush=True)
print('LIMIT: source-address helper, numerical formatter, whole keyboard preparation and retry convergence are not proved here.',flush=True)
