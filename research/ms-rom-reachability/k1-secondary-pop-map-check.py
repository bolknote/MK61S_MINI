#!/usr/bin/env python3
"""Inspect connected arithmetic/logical request routes, not keyboard search.

Stops at unforced data-dependent control; printed exact-copy sources are
solver-proved for arbitrary words. Does not assert native reachability.
"""
import runpy
from pathlib import Path
from z3 import And, Or, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
State,ex,base,keys,address=(q[n] for n in ('State','ex','base','keys','address'))
slots=q['slots']

def implies(p,claim):
    p.push();p.add(~claim);answer=p.check();p.pop()
    return answer==unsat

def inspect(start,marker,opcode):
    tag='pop_%s_%s_%02x_'%(start,marker,opcode)
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    following=slots[(slots.index(start)+1)%15]
    a=State(tag);a.m=pages[start];p=base(a,0x6E)
    p.add(a.r[29]==0,pages[following][31]==opcode%16,pages[following][34]==opcode//16)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker',marker) else pages[n][22]!=15)
    assert p.check()==sat
    route=[];writes=[]
    for i in range(120):
        p.push();ips=q['q']['possible_values'](address(a),p,257);p.pop()
        if len(ips)!=1:
            print('BOUND',start,marker,'%02X'%opcode, 'next',[hex(x) for x in ips],flush=True);break
        ip=ips[0];here=slots[(slots.index(start)+i)%15];nxt=slots[(slots.index(start)+i+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        a=ex(a,ip,*keys(tag+str(i)),serial_inputs=pages[nxt],emitted_outputs=out)
        if not implies(p,And(*[x==y for x,y in zip(out,old)])):
            sources=[n for n in slots if implies(p,And(*[out[1+3*j]==original[n][1+3*j] for j in range(12)]))]
            changed=[j for j in range(42) if not implies(p,out[j]==old[j])]
            writes.append({'ip':'%02X'%ip,'slot':here,'source':sources,'nibbles':changed})
        pages[here]=out
        if ip==0x39:
            assert implies(p,And(address(a)==0x6E,a.r[29]==0))
            print('CLOSED',start,marker,'%02X'%opcode,flush=True);break
    else:print('BOUND command count',start,marker,'%02X'%opcode,flush=True)
    print('PATH',' -> '.join(route),flush=True)
    print('WRITES',writes,flush=True)

if __name__=='__main__':
    for code in (0x10,0x37,0x38,0x39):
        inspect('marker','Z',code)
        inspect('V','V',code)
