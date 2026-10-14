#!/usr/bin/env python3
"""Where zero/guard/negative-exponent formatter suffixes write in the ring.

The native test establishes the physical 40 entry and marker locations.
All other serial words and per-tick keys are arbitrary; no forced next-IP
premises are inserted. This is a local suffix contract, not a full K1 proof.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
same=lambda xs,ys:And(*[x==y for x,y in zip(xs,ys)])
tetras=lambda value:[int(c,16) for c in reversed(value)]
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);outcome=p.check()
    assert outcome==unsat,(label,p.model() if outcome==sat else outcome)
    p.pop()

def check(tag,word,start,s1,middle,target,markers=('marker','V')):
    seq=[0x40,0x41,middle,0x46]
    def slot():return slots[(slots.index(start)+len(seq))%15]
    while slot() not in markers:seq.append(0xE5)
    seq += [0xE5,0xE6,0xE8,0xE7]
    names=[slots[(slots.index(start)+i)%15] for i in range(len(seq)+1)]
    pages=[State(tag+'_page_'+str(i)).m for i in range(len(seq)+1)]
    a=State(tag);a.m=pages[0];p=base(a,0x40)
    p.add(a.s1==s1,*[a.r[3*i]==v for i,v in enumerate(tetras(word))])
    for i,ip in enumerate(seq):
        if ip==0xE5:p.add(pages[i][22]==15 if names[i] in markers else pages[i][22]!=15)
    b=a
    for i,ip in enumerate(seq):
        label='%s %02X(%s)'%(tag,ip,names[i])
        prove(p,address(b)==ip,label+' forced next address')
        out=[];b=ex(b,ip,*keys(label),serial_inputs=pages[i+1],emitted_outputs=out)
        if ip==0xE7:
            assert names[i]==target
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(tetras(word))],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
                  label+' exactly twelve numeric writes, no other tetra changes')
            prove(p,same([b.r[3*j] for j in range(12)],[pages[i][1+3*j] for j in range(12)]),
                  label+' keeps the displaced word only in A')
        else:
            prove(p,same(out,pages[i]),label+' no ring writes')
            prove(p,same([b.r[3*j] for j in range(12)],tetras(word)),label+' retains the source word')
    prove(p,address(b)==0x47,tag+' returns to 47')
    print('PASS:',tag,word,len(seq),'connected commands from 40('+start+') write only '+target+' and return to 47.',flush=True)

check('zero','000000000000','P9',0,0x43,'P7')
check('guard','958912345678','Z',9,0x42,'X')
check('copy_minus99','901910000000','P8',9,0x42,'U',('marker','Y','V'))
