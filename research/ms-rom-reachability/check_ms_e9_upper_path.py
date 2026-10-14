#!/usr/bin/env python3
"""Conditional connected E9 upper writer; NOT keyboard reachability.

With the false marker in W, accepted control in Q and pending exchange
opcode 14h, the primary path copies visible X into upper Ms P7, not a
four-word push. This proof does not manufacture a native W marker.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);out=p.check()
    assert out==unsat,(label,p.model() if out==sat else out)
    p.pop();print('PASS:',label,flush=True)

def writer(marker_name,request=0x14):
    mark=slots.index(marker_name);start=(mark+1)%15
    target=slots[(mark+2)%15]
    seq=[0x9C,0x9E,0x9F,0xA0]
    current=lambda:slots[(start+len(seq))%15]
    while current()!='marker':seq.append(0xE5)
    seq.extend([0xE5,0xE6,0xED,0xEE,0xA1])
    while current()!=marker_name:seq.append(0xE5)
    seq.extend([0xE5,0xE6,0xE9])
    names=[slots[(start+i)%15] for i in range(len(seq)+1)]
    pages={n:State('e9_'+marker_name+'_'+n).m for n in slots}
    a=State('e9_'+marker_name);a.m=pages[names[0]];p=base(a,0x9C)
    control=pages[names[0]]
    p.add(a.r[30]==(request&15),a.r[33]==(request>>4),
          If(control[31]==15,UGE(control[34],1),UGE(control[34],7)))
    for name,ip in zip(names,seq):
        if ip==0xE5:p.add(pages[name][22]==15 if name in ('marker',marker_name) else pages[name][22]!=15)
    b=a
    for i,ip in enumerate(seq):
        label='%s: %02X(%s)'%(marker_name,ip,names[i])
        prove(p,address(b)==ip,label+' is forced')
        out=[];b=ex(b,ip,*keys(label+str(i)),serial_inputs=pages[names[i+1]],emitted_outputs=out)
        if ip==0xE9:
            prove(p,And(*[out[1+3*j]==pages['X'][1+3*j] for j in range(12)],
                         *[out[j]==pages[target][j] for j in range(42) if j%3!=1 or j>=37]),
                  label+' copies all 12 arbitrary X tetras, all other lanes/service held')
        else:prove(p,And(*[out[j]==pages[names[i]][j] for j in range(42)]),label+' ring held')
    prove(p,address(b)==0xA2,marker_name+' returns A2 at '+names[-1])
    print('CONTRACT:',marker_name,'marker -> X to',target,'in',len(seq),'connected commands',flush=True)

if __name__=='__main__':
    for marker_name in ['V','W']:writer(marker_name)
    print('LIMIT: conditional geometry, not native marker placement, keyboard timing, or a finished upper exchange.',flush=True)
