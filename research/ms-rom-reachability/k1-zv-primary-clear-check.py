#!/usr/bin/env python3
"""Locate the non-requesting clear at real/Z/V, before the Z/W push.

Local original-ROM execution only: no emulator state injection and no
claim that every accepted origin can be scheduled with native keys.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
S,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)

def check(start):
    tag='zv_clear_'+start
    pages={n:S(tag+n).m for n in slots}
    a=S(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==13,a.r[33]==0,a.s1==13,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z','V') else pages[n][22]!=15)
    route=[]
    def prove(claim):
        assert p.check()==sat
        p.push();p.add(~claim);assert p.check()==unsat;p.pop()
    for step in range(100):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop();assert len(ips)==1,(route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];next_=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));out=[]
        assert ip not in (0xEE,0xE9,0xA3,0xA8,0xD4,0xD6)
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[next_],emitted_outputs=out)
        if ip==0xE7:
            prove(And(*[out[1+3*j]==0 for j in range(12)],
                      *[out[j]==pages[here][j] for j in range(42) if j%3!=1 or j>=37]))
            print('PASS',start,'zeroes',here,'only twelve numeric tetras',flush=True)
            print('PATH',' -> '.join(route),flush=True)
            return here
        prove(And(*[x==y for x,y in zip(out,pages[here])]))
    raise AssertionError('no bounded E7')

if __name__=='__main__':
    for origin in ('control','T','W'):check(origin)
