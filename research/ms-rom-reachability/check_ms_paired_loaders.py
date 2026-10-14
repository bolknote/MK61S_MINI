#!/usr/bin/env python3
"""Connected ROM contracts for compensated D/E indirect recalls.

Entry fields/marker locations are native-test premises, not injected states.
Every next address is proved; source data and per-tick keys are arbitrary.
No formatter or whole safe-exit theorem is claimed here.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
A=lambda a:[a.r[3*i] for i in range(12)]
same=lambda xs,ys:And(*[x==y for x,y in zip(xs,ys)])
tetras=lambda s:[int(c,16) for c in reversed(s)]
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);outcome=p.check()
    assert outcome==unsat,(label,p.model() if outcome==sat else outcome)
    p.pop()

def route(start,carrier,pointer,normalized):
    seq=[0xD6]+[ip for _ in range(0 if normalized else 7) for ip in (0x2F,0x20)]+[0x2F,0x21,0x23,0x25]
    def slot():return slots[(slots.index(start)+len(seq))%15]
    def helper(index,load):
        while slot() not in ('marker','V'):seq.append(1)
        seq.extend([1]+[2]*(index+1)+[3,4,0xBA,0xCB,0xDD,0xD6 if load else 0xD4])
    helper(carrier,False)
    seq.extend([0x26,0x28,0x7E,0x70,0xAB,0xAD,0xA6])
    helper(pointer,True)
    seq.append(0xA7)
    while slot()!='marker':seq.append(0xE5)
    seq.extend([0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9])
    return seq

def check(start,carrier,pointer,normalized,source_index):
    tag='%s_%d_%d'%(start,pointer,normalized)
    seq=route(start,carrier,pointer,normalized)
    names=[slots[(slots.index(start)+i)%15] for i in range(len(seq)+1)]
    pages=[State('paired_'+tag+'_page_'+str(i)).m for i in range(len(seq)+1)]
    a=State('paired_'+tag);a.m=pages[0];p=base(a,0xD6)
    assert pointer<10 or normalized
    canon='0000%d0000000'%pointer;normal='0070000000%02d'%pointer
    p.add(a.r[29]==carrier+1,a.r[32]==carrier,a.r[35]==0,a.r[26]==15,a.s1==6,
          *[x==y for x,y in zip(stack(a),(0x2F,0xAC,0x9A))],
          *[a.m[3*i]==n for i,n in enumerate(tetras(normal if normalized else canon))])
    for i,ip in enumerate(seq):
        if ip in (1,0xE5):p.add(pages[i][22]==15 if names[i] in ('V','marker') else pages[i][22]!=15)
    b=a;source=None;carried=None;written=[]
    for i,ip in enumerate(seq):
        label=tag+' '+str(i)+' %02X(%s)'%(ip,names[i])
        prove(p,address(b)==ip,label+' is the forced next command')
        if ip==0xD6 and i:
            assert names[i]==slots[(7+source_index)%15]
            source=[pages[i][3*j] for j in range(12)]
        out=[];b=ex(b,ip,*keys(label),serial_inputs=pages[i+1],emitted_outputs=out)
        if ip==0xD4:
            prove(p,And(*[out[3*j]==v for j,v in enumerate(tetras(normal))],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=0 or j>=36]),label+' pointer write is exact M1 only')
        elif ip in (0xE7,0xA8):
            written.append(names[i]);incoming=source if ip==0xE7 else carried
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(incoming)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),label+' exact numeric swap, no other tetra changes')
            carried=[pages[i][1+3*j] for j in range(12)]
            prove(p,same(A(b),carried),label+' keeps the complete displaced word')
        else:prove(p,same(out,pages[i]),label+' makes no ring writes')
        if source is not None and carried is None:prove(p,same(A(b),source),label+' keeps all twelve source tetras')
    assert written==['X','Y','Z','T']
    prove(p,And(address(b)==0xAC,b.s1==0),tag+' finite stack lift returns to AC')
    print('PASS:',tag,len(seq),'connected commands; source ordinary P%d -> X; only pointer and visible stack writes.'%source_index,flush=True)

for start,carrier,pointer,source in [('Z',13,1,1),('P9',13,8,1),('T',14,2,2),('P10',14,9,2),('Z',13,3,3)]:
    for normalized in (False,True):check(start,carrier,pointer,normalized,source)
check('P9',13,10,True,3)
print('NOT a whole-keyboard or arbitrary-continuation theorem: initial markers and final formatting are native-test obligations.',flush=True)
