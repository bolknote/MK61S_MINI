#!/usr/bin/env python3
"""Connected IK1302 path from a native BC pointer read to the sixth-word store.

The keyboard test supplies the entry fields and physical marker positions.
Serial data and per-tick keys are otherwise arbitrary; no next-IP assumption
is inserted to force the path. This is not a whole-keyboard or safe-exit proof.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
A=lambda a:[a.r[3*i] for i in range(12)]
same=lambda xs,ys:And(*[x==y for x,y in zip(xs,ys)])
tetras=lambda value:[int(c,16) for c in reversed(value)]
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);result=p.check()
    if result!=unsat:
        print('FAILED:',label,'model:',p.model() if result==sat else result,flush=True)
    assert result==unsat,label
    p.pop()

def check(start):
    # D6 reads either ordinary C at Y, or ordinary P5 at Ms-page P8.
    seq=[0xD6]+[ip for _ in range(7) for ip in (0x2F,0x20)]+[0x2F,0x21,0x23,0x25]
    position=(slots.index(start)+len(seq))%15
    while slots[position]!='V':
        seq.append(1);position=(position+1)%15
    seq += [1]+[2]*13+[3,4,0xBA,0xCB,0xDD,0xD4,0x26,0x28,0x7E,0x71,0xAA]
    seq += [0xE5]*6+[0xE6,0xED,0xEE,0xAB,0xAD,0xA4]
    seq += [1,2,2,3,4,0xBA,0xCB,0xDD,0xD4]
    names=[slots[(slots.index(start)+i)%15] for i in range(len(seq)+1)]
    pages=[State('indirect_%s_page_%d'%(start,i)).m for i in range(len(seq)+1)]
    a=State('indirect_'+start);a.m=pages[0];p=base(a,0xD6)
    p.add(a.r[29]==13,a.r[32]==12,a.r[35]==1,a.r[26]==15,a.s1==6,
          *[x==y for x,y in zip(stack(a),(0x2F,0xAC,0x9A))],
          *[a.m[3*i]==n for i,n in enumerate(tetras('000010000000'))])
    for i,ip in enumerate(seq):
        if ip in (1,0xE5):
            p.add(pages[i][22]==15 if names[i] in ('V','marker') else pages[i][22]!=15)
    source=None;writes=[];b=a
    for i,ip in enumerate(seq):
        label='%s: %02X at %s, step %d'%(start,ip,names[i],i)
        prove(p,address(b)==ip,label+' is the forced next command')
        if ip==0xEE:
            assert names[i]=='P7'
            source=[pages[i][1+3*j] for j in range(12)]
        out=[]
        b=execute(b,ip,*keys('indirect_%s_keys_%d'%(start,i)),
                  serial_inputs=pages[i+1],emitted_outputs=out)
        if ip==0xD4:
            writes.append(names[i])
            expected=tetras('007000000001') if source is None else source
            prove(p,And(*[out[3*j]==n for j,n in enumerate(expected)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=0 or j>=36]),
                  label+' writes only the twelve exact M1 tetras')
        else:
            prove(p,same(out,pages[i]),label+' does not write the ring')
        if ip==0x25:
            prove(p,And(same(A(b),tetras('007000000001')),b.s1==4,stack(b)[0]==0x26),
                  label+' normalized pointer and return are exact')
        if ip==0x71:
            prove(p,And(b.r[30]==1,b.r[33]==4),label+' reconstructs direct store opcode 41')
        if source is not None and ip not in (0xDD,0xD4):
            prove(p,same(A(b),source),label+' keeps all twelve arbitrary source tetras')
    assert writes==['P8','V'],writes
    prove(p,address(b)==0xA5,start+' store returns to A5')
    print('PASS:',start,'pointer entry -> normalization -> D4(P8) -> AA(X1) -> EE(P7) -> D4(V/P1);',
          len(seq),'connected commands; exact arbitrary source; no M2/M3 writes.',flush=True)

for start in ('Y','P8'):check(start)
print('Native tests establish the D6 entries and marker-position premises. No intact-Ms exit is claimed.',flush=True)
