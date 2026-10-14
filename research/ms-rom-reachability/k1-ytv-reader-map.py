#!/usr/bin/env python3
"""Accepted primary reader origins: exact sources and push windows.

These maps stop at the formatter's late read; no native safe exit is implied.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
S,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop();assert answer==unsat,label

def reader(start,code,extra=('Y','T','V'),*,real=True):
    tag='ytv_reader_'+start+'_%02x'%code
    pages={n:S(tag+n).m for n in slots};original=dict(pages)
    a=S(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==code%16,a.r[33]==code//16,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    if code in (0x0E,0x0F):p.add(a.s1==code)
    if code==0x54:
        p.add(a.r[23]==0,a.r[26]==0,a.r[29]==4)
        for marker in (('marker',*extra) if real else extra):
            n=slots[(slots.index(marker)+1)%15]
            p.add(If(pages[n][31]==15,UGE(pages[n][34],1),UGE(pages[n][34],7)))
    if 0x60<=code<=0x6E:
        for n in slots:p.add(pages[n][21]!=15)
    markers=('marker',*extra) if real else extra
    for n in slots:p.add(pages[n][22]==15 if n in markers else pages[n][22]!=15)
    route=[];reads=[];writes=[];carried=None;register=None
    for step in range(150):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop();assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];following=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        if ip==0xEE:
            reads.append(here)
            if len(reads)==2:
                prove(p,And(a.st[36]==3,a.st[39]==14),'late E3 return')
                assert len(writes)==(0 if code==0x54 else 4)
                for n in slots:
                    if n not in writes:prove(p,And(*[x==y for x,y in zip(pages[n],original[n])]),'untouched '+n)
                result={'start':start,'code':'%02X'%code,'reads':reads,'register':register,'push':writes}
                print('PASS',result,flush=True);print('PATH',' -> '.join(route),flush=True);return result
            carried=[old[1+3*j] for j in range(12)]
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip==0xD6:
            register=here;carried=[old[3*j] for j in range(12)]
        if ip in (0xE7,0xA8):
            prove(p,And(*[out[1+3*j]==carried[j] for j in range(12)],
                *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact push '+here)
            writes.append(here);carried=[old[1+3*j] for j in range(12)]
        else:prove(p,And(*[x==y for x,y in zip(old,out)]),'no other output '+route[-1])
        pages[here]=out
    raise AssertionError('no late reader')

if __name__=='__main__':
    for code in (0x0E,0x0F):
        for origin in ('control','Z','U','W'):reader(origin,code)
    print('LIMIT: accepted local origin map only. No safe native hidden push or full-K1 claim.',flush=True)
