#!/usr/bin/env python3
"""Local ROM contracts for the shared BC/DC decimal-10 pointer pair.

Native tests must establish entry fields and marker locations. All next IPs
are proved from those premises, with arbitrary serial data and per-tick keys.
This does not prove the formatter or whole keyboard composition universally.
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

def route(start,pointer_raw,post_marker=False,capture=False):
    turns=7-int(pointer_raw[:3])
    pointer={'002011100000':111,'002011000000':110}.get(pointer_raw,10)
    index=pointer%100
    markers={'marker','V'}|({'X'} if post_marker else set())
    seq=[0xD6]+[ip for _ in range(turns) for ip in (0x2F,0x20)]+[0x2F,0x21,0x23,0x25]
    def slot():return slots[(slots.index(start)+len(seq))%15]
    def helper(n,load=False):
        while slot() not in markers:seq.append(1)
        seq.extend([1]+[2]*(n+1)+[3,4,0xBA,0xCB,0xDD,0xD6 if load else 0xD4])
    helper(12)
    seq.extend([0x26,0x28,0x7E,0x71 if capture else 0x70])
    if capture:
        seq.append(0xAA)
        while slot() not in markers:seq.append(0xE5)
        seq.extend([0xE5,0xE6,0xED,0xEE,0xAB,0xAD,0xA4])
        helper(index)
    else:
        seq.extend([0xAB,0xAD,0xA6]);helper(index,True)
        seq.append(0xA7)
        while slot() not in markers:seq.append(0xE5)
        seq.extend([0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9])
    return seq,markers,pointer

def check(start,pointer_raw,post_marker=False,capture=False,unsafe_canonical=False):
    tag='%s_%s_%d_%d'%(start,pointer_raw,post_marker,capture)
    seq,markers,pointer=route(start,pointer_raw,post_marker,capture)
    names=[slots[(slots.index(start)+i)%15] for i in range(len(seq)+1)]
    pages=[State('compact_'+tag+'_page_'+str(i)).m for i in range(len(seq)+1)]
    a=State('compact_'+tag);a.m=pages[0];p=base(a,0xD6)
    p.add(a.r[29]==13,a.r[32]==12,a.r[35]==int(capture),a.r[26]==15,a.s1==6,
          *[x==y for x,y in zip(stack(a),(0x2F,0xAC,0x9A))],
          *[a.m[3*i]==n for i,n in enumerate(tetras(pointer_raw))])
    for i,ip in enumerate(seq):
        if ip in (1,0xE5):p.add(pages[i][22]==15 if names[i] in markers else pages[i][22]!=15)
    b=a;source=None;carried=None;written=[]
    normalized=tetras('007%09d'%pointer)
    for i,ip in enumerate(seq):
        label=tag+' '+str(i)+' %02X(%s)'%(ip,names[i])
        prove(p,address(b)==ip,label+' is the forced next command')
        if capture and ip==0xEE:
            assert names[i]==('X' if unsafe_canonical else 'P7')
            source=[pages[i][1+3*j] for j in range(12)]
        if not capture and ip==0xD6 and i:
            assert names[i]==('P7' if pointer==111 else 'Q')
            source=[pages[i][3*j] for j in range(12)]
        out=[];b=ex(b,ip,*keys(label),serial_inputs=pages[i+1],emitted_outputs=out)
        if ip==0xD4:
            written.append(names[i])
            expected=source if capture and source is not None else normalized
            prove(p,And(*[out[3*j]==v for j,v in enumerate(expected)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=0 or j>=36]),
                  label+' writes exact M1 only')
        elif ip in (0xE7,0xA8):
            written.append(names[i]);incoming=source if ip==0xE7 else carried
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(incoming)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
                  label+' exact numeric swap, all other tetras unchanged')
            carried=[pages[i][1+3*j] for j in range(12)]
            prove(p,same(A(b),carried),label+' preserves the displaced word')
        else:prove(p,same(out,pages[i]),label+' makes no ring writes')
        if source is not None and carried is None and ip not in (0xDD,0xD4):
            prove(p,same(A(b),source),label+' keeps all twelve source tetras')
    expected_writes=['Y','Q'] if unsafe_canonical else (['P8','X1'] if capture else ['P8','X','Y','Z','T'])
    assert written==expected_writes,written
    prove(p,address(b)==(0xA5 if capture else 0xAC),tag+' finite return')
    if not capture:prove(p,b.s1==0,tag+' stack-lift mode reset')
    print('PASS:',tag,len(seq),'connected commands; writes',written,flush=True)

for start,word in [('Y','001010000000'),('P8','007000000010')]:
    check(start,word,capture=True)
    check(start,word)
check('Y','001010000000',post_marker=True)
check('U','002011100000',post_marker=True)
check('U','002011000000',post_marker=True)
check('P8','001010000000',capture=True,unsafe_canonical=True)
print('Seven positive local contracts and one wrong-base counterpath; native tests must establish entry/marker premises and the complete exit.',flush=True)
