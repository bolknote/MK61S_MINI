#!/usr/bin/env python3
"""Conditional connected EE-to-47 contract for canonical nonzero numbers.

Native tests supply the EE source, return fields, and declared marker map
(the default cloned map or the W/P9 pair during marker restoration).
This does not prove keyboard source selection or marker preparation.
"""
import runpy
import os
from pathlib import Path
from z3 import And, Or, UGE, ULE, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()

def check(header,z,small=False,origin='X',marker_mode='cloned'):
    assert origin in ('X','P8')
    assert marker_mode in ('cloned','W_P9','W_Z','W_T')
    if marker_mode=='W_P9':assert origin=='P8'
    if marker_mode in ('W_Z','W_T'):assert origin=='X'
    tag='format_%s_%s_%d_%d_%d'%(marker_mode,origin,header,z,small)
    seq=[int(x,16) for x in 'EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE'.split()]
    seq += [0xD9] if header==9 else ([0xD0,0xF2] if small else [0xD0])
    seq += [ip for _ in range(z+1) for ip in (0xF3,0xF7,0xF1)]
    seq += [ip for _ in range(8-z) for ip in (0xF4,0xF6)]+[0xF4,0xEA,0xEC]
    a=State(tag);p=base(a,0xEE)
    p.add(stack(a)[0]==0xE3,a.s1==13,a.r[38]==12,a.r[41]==15)
    source=[a.m[1+3*j] for j in range(12)]
    for i in list(range(8))+[9,10]:p.add(ULE(source[i],9))
    p.add(UGE(source[7],1),Or(source[8]==0,source[8]==9),source[11]==header,
          *[source[j]==0 for j in range(z)])
    if small:
        # Only fractional zeros may be suppressed in ordinary decimal
        # notation: z = min(actual trailing zeros, 7 - exponent).
        p.add(source[10]==0,ULE(source[9],7-z),Or(source[z]!=0,source[9]==7-z))
    else:
        p.add(source[z]!=0)
        if header==9:p.add(Or(source[9]!=0,source[10]!=0))
        else:p.add(Or(source[10]!=0,UGE(source[9],8)))
    b=a
    for i,ip in enumerate(seq):
        label=tag+' %d %02X'%(i,ip);prove(p,address(b)==ip,label+' forced address')
        previous=b.m;emitted=[]
        b=ex(b,ip,*keys(tag+'_key_'+str(i)),emitted_outputs=emitted)
        prove(p,And(*[x==y for x,y in zip(emitted,previous)]),label+' no ring writes')
    prove(p,address(b)==0x40,tag+' exit')
    prove(p,And(*[b.r[3*j]==source[j] for j in range(12)]),tag+' source')
    if header==9:prove(p,b.s1==9,tag+' scientific negative-exponent S1')
    if small:prove(p,b.s1==0,tag+' decimal S1')
    assert len(seq)==39+z+small
    # Complete the actual 40 -> E7 -> 47 suffix with the declared marker
    # arrangement. S1 is not guessed from the exponent.
    first=(slots.index(origin)+len(seq))%15;form=[0x40,0x41,0x42,0x46]
    markers={'cloned':{'marker','Y','Z','W'},'W_P9':{'W','P9'},
             'W_Z':{'marker','W','Z'},'W_T':{'marker','W','T'}}[marker_mode]
    while slots[(first+len(form))%15] not in markers:form.append(0xE5)
    form += [0xE5,0xE6,0xE8,0xE7]
    for i,ip in enumerate(form):
        where=slots[(first+i)%15];label=tag+' formatter %02X(%s)'%(ip,where)
        if ip==0xE5:p.add(b.m[22]==15 if where in markers else b.m[22]!=15)
        prove(p,address(b)==ip,label+' forced address')
        previous=b.m;out=[];b=ex(b,ip,*keys(label),emitted_outputs=out)
        if ip==0xE7:
            prove(p,And(*[out[1+3*j]==source[j] for j in range(12)],
                        *[out[j]==previous[j] for j in range(42) if j%3!=1 or j>=37]),
                  label+' exact source writes only the twelve numeric tetras')
        else:
            prove(p,And(*[x==y for x,y in zip(out,previous)],
                        *[b.r[3*j]==source[j] for j in range(12)]),label+' source held and no writes')
    prove(p,address(b)==0x47,tag+' final return')
    target=slots[(first+len(form)-1)%15]
    if marker_mode=='W_P9':expected='control' if z+small<=3 else 'P8'
    elif marker_mode=='W_Z':expected='V' if z+small<=4 else 'P8'
    elif marker_mode=='W_T':expected='W' if z+small<=5 else 'P8'
    else:expected=('U' if z+small<=3 else 'V' if z+small==4 else 'P8') if origin=='X' else ('X' if z+small<=5 else 'U')
    assert target==expected
    print('PASS: source %s, exponent header %d, decimal %d, suppressed zeros %d: EE -> 40 exactly %d commands, both signs and all canonical mantissas; no ring writes.'%
          (origin,header,small,z,len(seq)),flush=True)
    print('      Connected formatter writes only '+target+' and returns to 47.',flush=True)
    return seq

if __name__=='__main__':
    headers=[int(os.environ['MS_FORMAT_HEADER'])] if 'MS_FORMAT_HEADER' in os.environ else [9,0]
    zeros=[int(os.environ['MS_FORMAT_ZEROS'])] if 'MS_FORMAT_ZEROS' in os.environ else range(8)
    for header in headers:
        assert header in (0,9)
        for small in ([False] if header==9 else [False,True]):
            for z in zeros:
                assert 0<=z<=7
                check(header,z,small,os.environ.get('MS_FORMAT_SOURCE','X'),os.environ.get('MS_FORMAT_MARKERS','cloned'))
    print('LIMIT: EE-to-47 conditional contract; native key entry, marker preparation and whole keyboard timing remain separate obligations.',flush=True)
