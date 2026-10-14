#!/usr/bin/env python3
"""Conditional LastX from real/Z/T/V, accepted at real control.

Proves both readers and the intervening push. Keyboard selection and
inter-chip timing require a native test; they are not assumptions about
the observed calculator imposed by this proof.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat
root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)

def check():
    tag='single_v_lastx';pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages['control'];p=base(a,0x9C)
    p.add(a.r[30]==15,a.r[33]==0,a.s1==15,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z','T','V') else pages[n][22]!=15)
    def prove(claim):
        assert p.check()==sat
        p.push();p.add(~claim);answer=p.check();p.pop();assert answer==unsat
    path=[];reads=[];writes=[];carried=None
    for step in range(150):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop()
        assert len(ips)==1,(path,ips)
        ip=ips[0];here=slots[(1+step)%15];following=slots[(2+step)%15];old=pages[here]
        path.append('%02X(%s)'%(ip,here))
        if ip==0xEE:
            reads.append(here)
            if len(reads)==1:
                assert here=='U',path
                carried=[old[1+3*j] for j in range(12)]
            else:
                assert reads==['U','P7'] and writes==['X','Y','Z','T'],(path,reads,writes)
                prove(And(a.st[36]==3,a.st[39]==14))
                for dest,src in zip(writes,['U','X','Y','Z']):
                    prove(And(*[pages[dest][1+3*j]==original[src][1+3*j] for j in range(12)]))
                for n in slots:
                    prove(pages[n][22]==15 if n in ('marker','T','V') else pages[n][22]!=15)
                print('PASS accepted control: EE(U), exact visible push, late EE(P7)/E3.',flush=True)
                print('PATH',' -> '.join(path),flush=True)
                return
        out=[];a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip in (0xE7,0xA8):
            prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                      *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]))
            carried=[old[1+3*j] for j in range(12)];writes.append(here)
        else:prove(And(*[x==y for x,y in zip(out,old)]))
        pages[here]=out
    raise AssertionError('no bounded second reader')

if __name__=='__main__':
    check()
    formatter=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    formatter(9,7,source_slot='P7',marker_slots=('marker','T','V'),target_by_class=['X']*7+['W']*2)
    print('CONDITIONAL END: X/Y/Z/T=v/u/q/m, Ms U/V/W/Q=v/m/a/p; no native entry is asserted.',flush=True)
