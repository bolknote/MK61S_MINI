#!/usr/bin/env python3
"""Local ROM contracts for a different second entry, not a full K1 proof."""
import runpy
from pathlib import Path
from z3 import And, sat, unsat

root=Path(__file__).resolve().parent
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']


def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop()
    assert answer==unsat,label


def remove_y():
    q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
    State,ex,base,keys,address=(q[n] for n in ('State','ex','base','keys','address'))
    pages={n:State('only_y_swap_'+n).m for n in slots};original=dict(pages)
    a=State('only_y_swap');a.m=pages['Y'];p=base(a,0x6E)
    p.add(a.r[29]==0,pages['Z'][34]==1,pages['Z'][31]==4)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Y') else pages[n][22]!=15)
    route=[];writes=[];acks=[]
    for step in range(80):
        p.push();ips=q['q']['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(4+step)%15];nxt=slots[(5+step)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        a=ex(a,ip,*keys('only_y_swap_'+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip in (0x4E,0x2A):
            target,source=('X','V') if ip==0x4E else ('Y','X')
            assert here==target
            prove(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact '+source+' -> '+target)
            writes.append((target,source))
        elif ip==0x27:
            assert here=='control'
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only real-control ACK')
            acks.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no undeclared output '+route[-1])
        pages[here]=out
        if ip==0x39:
            prove(p,And(address(a)==0x6E,a.r[29]==0),'quiet return');break
    else:raise AssertionError('no bounded return')
    assert writes==[('X','V'),('Y','X')] and acks==['control']
    for n in slots:
        prove(p,pages[n][22]==15 if n=='marker' else pages[n][22]!=15,'only true marker remains')
    print('PASS Y-only swap: V -> X, old X -> Y; all stored words held.',flush=True)
    print('PATH',' -> '.join(route),flush=True)


if __name__=='__main__':
    producer=runpy.run_path(str(root/'k1-u-reserve-control-mask-check.py'))['producer']
    producer('control',0x25,('T','U'),'W','X1','U')
    rotate=runpy.run_path(str(root/'k1-upper-replay-map-check.py'))['rotation']
    rotate('T',('T','U'),[('W','Q'),('Q','P7'),('P7','P8'),('P8','W')],['U','U'])
    producer('U',0x25,('T','U'),'X','V','control')
    rotate('marker',('T','U'),[('X','Y'),('Y','Z'),('Z','T'),('T','X')],['control','control'])
    producer('T',0x25,('Z','U'),'X','U','control')
    rotate('marker',('Z','U'),[('X','Y'),('Y','Z'),('Z','T'),('T','X')],['control','control'])
    producer('control',0x14,('Y',),'X','X1','Z')
    remove_y()
    formatter=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    formatter(9,1,source_slot='Q',marker_slots=('marker','T','U'),target_by_class=['X']*8+['W'])
    formatter(9,1,source_slot='X',marker_slots=('marker','Z','U'),
              target_by_class=['V']*5+['Q']*2+['X']*2)
    formatter(9,0,source_slot='X',marker_slots=('marker','Y'),target_by_class=['U']*4+['X']*5)
    formatter(9,1,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    formatter(0,5,True,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    print('LIMIT: local symbolic contracts; actual inter-chip timing and continuous entry must be checked natively. No universal repeatability or full K1.',flush=True)
