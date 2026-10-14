#!/usr/bin/env python3
"""Conditional, connected ROM contract for a zero-guarded W/Q exchange.

The native checker must establish the entries and actual scheduling.
No arithmetic absorption theorem or full K1/clean-exit claim is made.
"""
import runpy
from pathlib import Path
from z3 import And, sat, unsat

root=Path(__file__).resolve().parent
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop()
    assert answer==unsat,label

def secondary():
    q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
    State,ex,base,keys,address=(q[n] for n in ('State','ex','base','keys','address'))
    pages={n:State('zero_swap_secondary_'+n).m for n in slots};original=dict(pages)
    a=State('zero_swap_secondary');a.m=pages['T'];p=base(a,0x6E)
    p.add(a.r[29]==0,pages['U'][34]==1,pages['U'][31]==4)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','T') else pages[n][22]!=15)
    path=[];writes=[];ack=[]
    for step in range(80):
        p.push();ips=q['q']['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',path,ips)
        ip=ips[0];here=slots[(6+step)%15];nxt=slots[(7+step)%15]
        path.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        a=ex(a,ip,*keys('zero_swap_secondary_'+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip in (0x4E,0x2A):
            target,source=('W','Q') if ip==0x4E else ('Q','W')
            assert here==target
            prove(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact '+source+' -> '+target)
            writes.append((target,source))
        elif ip==0x27:
            assert here=='U'
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only U ACK')
            ack.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no other output change at '+path[-1])
        pages[here]=out
        if ip==0x39:
            prove(p,And(address(a)==0x6E,a.r[29]==0),'quiet return')
            break
    else:raise AssertionError('unclosed secondary path')
    assert writes==[('W','Q'),('Q','W')] and ack==['U']
    print('PASS secondary:', ' -> '.join(path),flush=True)
    print('RESULT: arbitrary twelve-tetra W/Q swap, U ACK, no other ring changes.',flush=True)

if __name__=='__main__':
    producer=runpy.run_path(str(root/'k1-u-reserve-control-mask-check.py'))['producer']
    producer('control',0x14,('T',),'W','X1','U')
    secondary()
    formatter=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    formatter(0,7,True,True,source_slot='X',marker_slots=('marker','T'),target_by_class=['W']*6+['X']*3)
    clear_t=runpy.run_path(str(root/'k1-y-t-swap-v-path-check.py'))['clear_t']
    clear_t('control');clear_t('U')
    formatter(9,1,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    print('LIMIT: accepted 9C(control), 6E(T)/R29=0 and zero EE(X)/top E3; '
          'two conditional RCL0 entries and its separate class-1 formatter; '
          'native entry/timing and the earlier arithmetic prefix are separate obligations.',flush=True)
