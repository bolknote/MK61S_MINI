#!/usr/bin/env python3
"""Conditional full formatter when the physical EE source is hidden Q.

Use the already established canonical normalization path, but verify it
again connected to the actual Y/U marker geometry. This is not a proof
of the keyboard prefix or of a completed Q exchange.
"""
import os
import runpy
from pathlib import Path
from z3 import And, Or, UGE, ULE, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);result=p.check()
    assert result==unsat,(label,p.model() if result==sat else result)
    p.pop()

def check(header,z,small=False,zero=False,*,source_slot='Q',
          marker_slots=('marker','Y','U'),target_by_class=None):
    tag='q_formatter_%d_%d_%d_%d'%(header,z,small,zero)
    a=State(tag);p=base(a,0xEE);p.add(a.st[36]==3,a.st[39]==14)
    source=[a.m[1+3*j] for j in range(12)]
    if zero:p.add(*[v==0 for v in source])
    else:
        for i in list(range(8))+[9,10]:p.add(ULE(source[i],9))
        p.add(UGE(source[7],1),Or(source[8]==0,source[8]==9),source[11]==header,
              *[source[j]==0 for j in range(z)])
        if small:p.add(source[10]==0,ULE(source[9],7-z),Or(source[z]!=0,source[9]==7-z))
        else:
            p.add(source[z]!=0)
            if header==9:p.add(Or(source[9]!=0,source[10]!=0))
            else:p.add(Or(source[10]!=0,UGE(source[9],8)))
    seq=[int(x,16) for x in 'EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE'.split()]
    seq += [0xD9] if header==9 else ([0xD0,0xF2] if small else [0xD0])
    seq += [ip for _ in range(z+1) for ip in (0xF3,0xF7,0xF1)]
    seq += [ip for _ in range(8-z) for ip in (0xF4,0xF6)]+[0xF4,0xEA,0xEC]
    b=a
    for i,ip in enumerate(seq):
        label=tag+' step %d %02X'%(i,ip);prove(p,address(b)==ip,label+' forced next address')
        old=b.m;out=[];b=ex(b,ip,*keys(label),emitted_outputs=out)
        prove(p,And(*[x==y for x,y in zip(out,old)]),label+' no ring writes')
    prove(p,And(address(b)==0x40,*[b.r[3*j]==source[j] for j in range(12)]),tag+' exact source survives')
    assert len(seq)==39+z+int(small)
    if zero:assert len(seq)==47
    first=(slots.index(source_slot)+len(seq))%15
    form=[0x40,0x41,0x43 if zero else 0x42,0x46]
    markers=set(marker_slots)
    while slots[(first+len(form))%15] not in markers:form.append(0xE5)
    form += [0xE5,0xE6,0xE8,0xE7]
    for j,ip in enumerate(form):
        where=slots[(first+j)%15];label=tag+' %02X(%s)'%(ip,where)
        if ip==0xE5:p.add(b.m[22]==15 if where in markers else b.m[22]!=15)
        prove(p,address(b)==ip,label+' forced next address')
        old=b.m;out=[];b=ex(b,ip,*keys(label),emitted_outputs=out)
        if ip==0xE7:
            prove(p,And(*[out[1+3*k]==source[k] for k in range(12)],
                        *[out[k]==old[k] for k in range(42) if k%3!=1 or k>=37]),
                  label+' only exact 12-tetra source is written')
        else:prove(p,And(*[x==y for x,y in zip(out,old)],*[b.r[3*k]==source[k] for k in range(12)]),
                   label+' source held and no writes')
    prove(p,address(b)==0x47,tag+' returns to 47')
    target=slots[(first+len(form)-1)%15];qvalue=z+int(small)
    assert target==(target_by_class[qvalue] if target_by_class is not None else ('U' if qvalue==8 else 'X'))
    print('PASS connected formatter:',{'source':source_slot,'markers':sorted(markers),
          'header':header,'suppressedZeros':z,'decimal':small,
          'zero':zero,'class':qvalue,'target':target,'numericTetras':12},flush=True)

if __name__=='__main__':
    selected=os.environ.get('K1_Q_FORMAT_CASES')
    cases=[tuple(map(int,part.split(','))) for part in selected.split(';')] if selected else [
        (h,z,int(s)) for h in (9,0) for s in ([False] if h==9 else [False,True]) for z in range(8)]
    for h,z,s in cases:check(h,z,bool(s))
    if not selected:check(0,7,True,True)
    print('LIMIT: physical EE(Q), top E3, fixed marker geometry; no native entry/cleanup guarantee.',flush=True)
