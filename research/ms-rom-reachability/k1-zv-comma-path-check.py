#!/usr/bin/env python3
"""Local cached-editor contract for positive three-digit a ending nonzero.

This starts at an accepted 9C(T or W), not an imported emulator snapshot.
Control/cache fields are explicit conditions from the native trace. The
three significant digits and every other ring payload are symbolic.
"""
import runpy
from pathlib import Path
from z3 import And, BitVec, If, UGE, ULE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
S,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)

def check(start):
    tag='zv_comma_'+start
    pages={n:S(tag+n).m for n in slots};original=dict(pages)
    initial=S(tag);initial.m=pages[start];a=initial;p=base(a,0x9C)
    # Conditions at the accepted gate; payload digits are deliberately free.
    rv=[15,2,0,15,3,10,15,4,10,15,5,10,15,6,10,2,7,10,0,8,10,
        4,9,0,15,9,0,15,9,10,10,5,0,0,2,15,12,2,13,9,6,0]
    st=[0,10,0,0,10,8,0,10,8,0,10,8,0,10,8,2,10,8,0,10,8,
        4,0,0,0,0,0,15,2,0,15,0,0,15,0,0,10,8,15,9,9,4]
    digits=[BitVec(tag+'_digit'+str(j),4) for j in range(3)]
    p.add(*[ULE(d,9) for d in digits],UGE(digits[0],1),UGE(digits[2],1))
    for i,d in zip((15,18,21),reversed(digits)):rv[i]=st[i]=d
    # These pre-restoration R cache residues depend on other fixture words;
    # leave them arbitrary rather than accidentally freezing one dataset.
    free_r={1,4,7,10,13,16,19,28}
    p.add(*[x==y for j,(x,y) in enumerate(zip(a.r,rv)) if j not in free_r],
          *[x==y for x,y in zip(a.st,st)],a.s==12,a.s1==10)
    p.add(If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z','V') else pages[n][22]!=15)
    source=[0]*5+list(reversed(digits))+[0,2,0,0]
    p.add(*[pages['X'][1+3*j]==source[j] for j in range(12)])
    route=[]
    def prove(claim,label):
        assert p.check()==sat,('empty premise',label)
        p.push();p.add(~claim);answer=p.check();p.pop();assert answer==unsat,label
    for step in range(70):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop();assert len(ips)==1,(route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];following=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here))
        assert ip not in (0xEE,0xE9,0xA3,0xA8,0xD4,0xD6)
        old=pages[here];out=[]
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip==0xE7:
            assert here=='V'
            prove(And(*[out[1+3*j]==source[j] for j in range(12)],
                      *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact cached a to V')
            prove(addr(a)==0x47,'return to 47')
            pages[here]=out
            for n in slots:
                if n!='V':prove(And(*[x==y for x,y in zip(pages[n],original[n])]),'held '+n)
            print('PASS cached comma:',start,'positive three-digit a ending nonzero; only 12 V tetras',flush=True)
            print('PATH',' -> '.join(route),flush=True)
            return
        prove(And(*[x==y for x,y in zip(out,old)]),'no other ring write '+route[-1])
        pages[here]=out
    raise AssertionError('no bounded editor copy')

if __name__=='__main__':
    for start in ('T','W'):check(start)
    fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    fmt(0,5,True,source_slot='X',marker_slots=('marker','Z'),target_by_class=['X']*9)
    print('LIMIT: fixed accepted cached-editor conditions; not arbitrary a, timing, or a closed K1.',flush=True)
