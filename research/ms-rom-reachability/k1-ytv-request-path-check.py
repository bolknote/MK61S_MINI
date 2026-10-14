#!/usr/bin/env python3
"""Classify accepted primary requests with real/Y/T/V markers.

Finite scanner-origin analysis, not keyboard sequence enumeration. The
precondition is local: native scheduling/reachability remain separate.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop();assert answer==unsat,label

def request(start,code=0x25,extra=('Y','T','V'),*,real=True):
    tag='ytv_request_'+start+'_%02x'%code
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==code%16,a.r[33]==code//16,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    markers=('marker',*extra) if real else extra
    for n in slots:p.add(pages[n][22]==15 if n in markers else pages[n][22]!=15)
    route=[];reads=[];writes=[]
    for step in range(100):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];following=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        if ip==0xEE:reads.append(here)
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip==0xE9:
            assert len(reads)==1
            prove(p,And(*[out[1+3*j]==original[reads[0]][1+3*j] for j in range(12)],
                *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact reserve '+here)
            writes.append(('E9',here))
        elif ip==0xA3:
            prove(p,And(out[28]==original[reads[0]][28],out[31]==code%16,out[34]==code//16,
                *[out[j]==old[j] for j in range(42) if j not in (28,31,34)],addr(a)==0xD3),'exact request '+here)
            writes.append(('A3',here))
        else:prove(p,And(*[x==y for x,y in zip(old,out)]),'no other write '+route[-1])
        pages[here]=out
        if ip==0xA3:
            result={'start':start,'code':'%02X'%code,'reads':reads,'writes':writes}
            print('PASS',result,flush=True);print('PATH',' -> '.join(route),flush=True)
            return result
    raise AssertionError('no bounded request')

if __name__=='__main__':
    for origin in ('control','Z','U','W'):request(origin)
    print('LIMIT: accepted primary paths only; no safe native upper operation established.',flush=True)
