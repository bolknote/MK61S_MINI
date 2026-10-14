#!/usr/bin/env python3
"""Connected IK1302 contracts: C=7/P5=normalized 7, post-marker C=7/P0=0.

The physical ordinary P0 is the zero data source as well as the late pointer.
Only entry fields and tested marker bits are constrained; serial pages and
keyboard inputs are otherwise arbitrary. Native integration supplies P0=0.
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

def route(start,word,post_marker=False):
    pointer=0 if word=='000000000000' else 7
    markers={'marker','V'}|({'X'} if post_marker else set())
    seq=[0xD6]+[ip for _ in range(7-int(word[:3])) for ip in (0x2F,0x20)]+[0x2F,0x21,0x23,0x25]
    def slot():return slots[(slots.index(start)+len(seq))%15]
    def helper(n,load=False):
        while slot() not in markers:seq.append(1)
        seq.extend([1]+[2]*(n+1)+[3,4,0xBA,0xCB,0xDD,0xD6 if load else 0xD4])
    helper(12);seq.extend([0x26,0x28,0x7E,0x70,0xAB,0xAD,0xA6]);helper(pointer,True)
    seq.append(0xA7)
    while slot() not in markers:seq.append(0xE5)
    seq.extend([0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9])
    return seq,markers,pointer

def check(start,word,post_marker=False):
    tag='%s_%s_%d'%(start,word,post_marker)
    seq,markers,pointer=route(start,word,post_marker)
    names=[slots[(slots.index(start)+i)%15] for i in range(len(seq)+1)]
    pages=[State('zero_'+tag+'_page_'+str(i)).m for i in range(len(seq)+1)]
    a=State('zero_'+tag);a.m=pages[0];p=base(a,0xD6)
    p.add(a.r[29]==13,a.r[32]==12,a.r[35]==0,a.r[26]==15,a.s1==6,
          *[x==y for x,y in zip(stack(a),(0x2F,0xAC,0x9A))],
          *[a.m[3*i]==n for i,n in enumerate(tetras(word))])
    for i,ip in enumerate(seq):
        if ip in (1,0xE5):p.add(pages[i][22]==15 if names[i] in markers else pages[i][22]!=15)
    b=a;source=None;carried=None;written=[]
    for i,ip in enumerate(seq):
        label=tag+' '+str(i)+' %02X(%s)'%(ip,names[i])
        prove(p,address(b)==ip,label+' forced next command')
        if ip==0xD6 and i:
            assert names[i]=='U','the ordinary P0 source must be selected in both bases'
            source=[pages[i][3*j] for j in range(12)]
        out=[];b=ex(b,ip,*keys(label),serial_inputs=pages[i+1],emitted_outputs=out)
        if ip==0xD4:
            written.append(names[i])
            prove(p,And(*[out[3*j]==v for j,v in enumerate(tetras('007%09d'%pointer))],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=0 or j>=36]),
                  label+' normalizes only twelve M1 tetras')
        elif ip in (0xE7,0xA8):
            written.append(names[i]);incoming=source if ip==0xE7 else carried
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(incoming)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
                  label+' exact numeric swap with no other writes')
            carried=[pages[i][1+3*j] for j in range(12)]
            prove(p,same(A(b),carried),label+' displaced word retained')
        else:prove(p,same(out,pages[i]),label+' no ring writes')
        if source is not None and carried is None:
            prove(p,same(A(b),source),label+' source stays intact')
    assert written==[('Y' if pointer==0 else 'P8'),'X','Y','Z','T'],written
    prove(p,And(address(b)==0xAC,b.s1==0),tag+' finite return and stack-lift reset')
    print('PASS:',tag,len(seq),'connected commands; P0 source; writes',written,flush=True)

if __name__=='__main__':
    check('Y','000070000000')
    check('P8','007000000007')
    check('Y','000070000000',True)
    check('U','000000000000',True)
    print('Four local zero-loader contracts; no theorem about arbitrary keyboard entry or whole K1.',flush=True)
