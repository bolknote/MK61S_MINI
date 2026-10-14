#!/usr/bin/env python3
"""Conditional Y/T/V entry: LastX(Q), visible lift, then a clears V.

This proves a ROM suffix; keyboard preparation/native interaction are
separately audited by k1-z-backed-lastx-check.cjs (29 September).
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
tag='y_v_lastx';pages={n:State(tag+'_'+n).m for n in slots};original=dict(pages)
a=State(tag);a.m=pages['Z'];p=base(a,0x9C)
p.add(a.r[30]==15,a.r[33]==0,a.s1==15,
      If(pages['Z'][31]==15,UGE(pages['Z'][34],1),UGE(pages['Z'][34],7)))
for n in slots:p.add(pages[n][22]==15 if n in ('marker','Y','T','V') else pages[n][22]!=15)

def prove(claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim);result=p.check();p.pop();assert result==unsat,label

route=[];reads=[];writes=[];carried=None
for step in range(100):
    p.push();ips=q['possible_values'](addr(a),p,257);p.pop()
    assert len(ips)==1,('unforced route',route,ips)
    ip=ips[0];here=slots[(slots.index('Z')+step)%15]
    following=slots[(slots.index('Z')+step+1)%15];old=pages[here]
    route.append('%02X(%s)'%(ip,here))
    if ip==0xEE:
        reads.append(here)
        if len(reads)==1:
            assert here=='Q',route
            carried=[old[1+3*j] for j in range(12)]
        if len(reads)==2:
            assert here=='P7',route
            prove(And(a.st[36]==3,a.st[39]==14),'late EE returns to E3')
            assert writes==['X','Y','Z','T'],writes
            for dest,source in zip(['X','Y','Z','T'],['Q','X','Y','Z']):
                prove(And(*[pages[dest][1+3*j]==original[source][1+3*j] for j in range(12)]),
                      'result '+dest+' <- '+source)
            for n in slots:
                prove(pages[n][22]==15 if n in ('marker','Z','V') else pages[n][22]!=15,
                      'post-push marker geometry '+n)
            for n in slots:
                if n not in writes:prove(And(*[x==y for x,y in zip(pages[n],original[n])]),'untouched '+n)
            print('PASS connected accepted 9C(Z) -> EE(Q) -> exact visible push -> EE(P7)/E3.',flush=True)
            print('PASS after push: X/Y/Z/T=oldQ/oldX/oldY/oldZ; markers real/Z/V; other fields held.',flush=True)
            print('PATH',' -> '.join(route),flush=True)
            break
    out=[];a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
    if ip in (0xE7,0xA8):
        prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                  *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact '+route[-1])
        carried=[old[1+3*j] for j in range(12)];writes.append(here)
    else:prove(And(*[x==y for x,y in zip(out,old)]),'no other write '+route[-1])
    pages[here]=out
else:raise AssertionError('no late EE')

formatter=runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
targets=['X']*7+['V']*2
for header,zeros,small,zero in [(9,7,False,False),(0,7,False,False),
                               (0,6,True,False),(0,7,True,False),(0,7,True,True)]:
    formatter(header,zeros,small,zero,source_slot='P7',marker_slots=('marker','Z','V'),
              target_by_class=targets)
print('PASS all five canonical class-7/8 cases incl zero: late exact E7(V)=a, clearing V marker.',flush=True)
print('CONDITIONAL END: visible p/u/m/q; Ms U/V/W/Q=v/a/q/p; upper a/b/c/d; only real/Z markers.',flush=True)
print('LIMIT of this proof: local primary suffix only. Separate native audit exists; no closed exit or full K1 proved.',flush=True)
