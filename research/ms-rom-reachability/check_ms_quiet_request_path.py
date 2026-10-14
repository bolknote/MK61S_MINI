#!/usr/bin/env python3
"""Connected 28h primary producer and quiet secondary request decoder.

The local data is arbitrary. Keyboard entry, formatter return and the third
chip are separate native-test obligations; this is not a full K1 writer.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ULE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop();print('PASS:',label,flush=True)

pages={n:State('quiet_primary_'+n).m for n in slots}
a=State('quiet_primary');a.m=pages['Q'];p=base(a,0x9C)
p.add(a.r[30]==8,a.r[33]==2,
      If(pages['Q'][31]==15,UGE(pages['Q'][34],1),UGE(pages['Q'][34],7)))
seq=[0x9C,0x9E,0x9F,0xA0,0xE5,0xE5,0xE6,0xED,0xEE,0xA1,0xE5,0xE6,0xE9,0xA2,0xA2,0xA3]
for i,ip in enumerate(seq):
    name=slots[(10+i)%15]
    if ip in (0xE5,0xA2):p.add(pages[name][22]==15 if name in ('marker','Z','W') else pages[name][22]!=15)
b=a
for i,ip in enumerate(seq):
    name=slots[(10+i)%15];label='primary %02X(%s)'%(ip,name)
    prove(p,address(b)==ip,label+' is forced')
    out=[];b=ex(b,ip,*keys('quiet_primary_'+str(i)),serial_inputs=pages[slots[(11+i)%15]],emitted_outputs=out)
    if ip==0xE9:
        prove(p,And(*[out[1+3*j]==pages['X'][1+3*j] for j in range(12)],
                    *[out[j]==pages[name][j] for j in range(42) if j%3!=1 or j>=37]),
              label+' copies exactly twelve arbitrary X tetras')
    elif ip==0xA3:
        prove(p,And(out[34]==2,out[31]==8,out[28]==pages['X'][28],
                    *[out[j]==pages[name][j] for j in range(42) if j not in (28,31,34)]),
              label+' writes only request 28 plus source header tetra')
    else:prove(p,And(*[x==y for x,y in zip(out,pages[name])]),label+' holds the entire ring page')
prove(p,address(b)==0xD3,'primary returns D3 at P7 after request submission')

secondary=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
State,ex,base,keys=(secondary[n] for n in ('State','ex','base','keys'))
names=['W','Q','P7','P8','P9','P10','marker','control','X1','X']
pages=[State('quiet_secondary_'+n).m for n in names]
a=State('quiet_secondary');a.m=pages[0];p=base(a,0x6E)
p.add(a.r[29]==0,pages[0][22]==15,pages[1][34]==2,UGE(pages[1][31],6),ULE(pages[1][31],14))
b=a
for i,ip in enumerate([0x6E,0x5E,0x50,0x52,0x53,0x4F,0x24,0x26,0x39]):
    label='secondary %02X(%s)'%(ip,names[i]);prove(p,address(b)==ip,label+' is forced')
    out=[];b=ex(b,ip,*keys('quiet_secondary_'+str(i)),serial_inputs=pages[i+1],emitted_outputs=out)
    prove(p,And(*[x==y for x,y in zip(out,pages[i])]),label+' holds all 42 tetras')
prove(p,And(address(b)==0x6E,b.r[29]==0),'26h..2Eh requests return to 6E with R29=0 after nine commands, without writes')
print('LIMIT: accepted primary Q and secondary W entry are conditional. Native tests must establish them and cover IK1306 and all later writes.',flush=True)
