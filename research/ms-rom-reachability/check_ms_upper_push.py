#!/usr/bin/env python3
"""Connected IK1302 upper-stack writer, compensated through D and P6.

The input source and four Ms words are arbitrary. Native tests supply entry
fields and marker placement; no whole-keyboard/formatter theorem is claimed.
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

def check(start,word,pointer,source_slot='X1'):
    seq=[0xD6]+[ip for _ in range(7-int(word[:3])) for ip in (0x2F,0x20)]+[0x2F,0x21,0x23,0x25]
    def slot():return slots[(slots.index(start)+len(seq))%15]
    def helper(n,load=False):
        while slot() not in ('marker','V'):seq.append(1)
        seq.extend([1]+[2]*(n+1)+[3,4,0xBA,0xCB,0xDD,0xD6 if load else 0xD4])
    helper(13);seq.extend([0x26,0x28,0x7E,0x70,0xAB,0xAD,0xA6]);helper(pointer,True)
    seq.append(0xA7)
    while slot() not in ('marker','V'):seq.append(0xE5)
    seq.extend([0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9])
    names=[slots[(slots.index(start)+i)%15] for i in range(len(seq)+1)]
    pages=[State('upper_push_'+start+'_page_'+str(i)).m for i in range(len(seq)+1)]
    a=State('upper_push_'+start);a.m=pages[0];p=base(a,0xD6)
    p.add(a.r[29]==14,a.r[32]==13,a.r[35]==0,a.r[26]==15,a.s1==6,
          *[x==y for x,y in zip(stack(a),(0x2F,0xAC,0x9A))],
          *[a.m[3*i]==n for i,n in enumerate(tetras(word))])
    for i,ip in enumerate(seq):
        if ip in (1,0xE5):p.add(pages[i][22]==15 if names[i] in ('marker','V') else pages[i][22]!=15)
    b=a;source=None;carried=None;writes=[];ms=[];return_fields=None
    for i,ip in enumerate(seq):
        label=start+' '+str(i)+' %02X(%s)'%(ip,names[i])
        prove(p,address(b)==ip,label+' is the forced next command')
        if ip==0xD6 and i:
            assert names[i]==source_slot;source=[pages[i][3*j] for j in range(12)]
        if ip==0xA9:return_fields=(b.r[32],b.r[35])
        out=[];b=ex(b,ip,*keys(label),serial_inputs=pages[i+1],emitted_outputs=out)
        if ip==0xD4:
            writes.append(names[i])
            prove(p,And(*[out[3*j]==v for j,v in enumerate(tetras('007%09d'%pointer))],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=0 or j>=36]),label+' exact pointer write')
        elif ip in (0xE7,0xA8):
            writes.append(names[i]);ms.append([pages[i][1+3*j] for j in range(12)])
            incoming=source if ip==0xE7 else carried
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(incoming)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),label+' exact numeric swap only')
            carried=ms[-1];prove(p,same(A(b),carried),label+' retains displaced word')
        else:prove(p,same(out,pages[i]),label+' no ring writes')
        if source is not None and carried is None:prove(p,same(A(b),source),label+' all twelve source tetras retained')
    assert writes==[('Z' if start=='Z' else 'P9'),'P7','P8','P9','P10']
    prove(p,And(address(b)==0xAC,b.s1==0,same(A(b)[:10],ms[-1][:10]),
                b.r[30]==return_fields[0],b.r[33]==return_fields[1]),
          start+' finite return; A9 replaces two high displaced-word tetras, not the already written Ms words')
    print('PASS:',start,word,len(seq),'connected commands; M1('+source_slot+') -> P7; old P7/P8/P9 -> P8/P9/P10; services/M3 unchanged.',flush=True)

check('Z','007000000010',10)
check('P9','000020000000',2)
check('Z','007000000011',11,'X')
check('P9','000030000000',3,'X')
print('ALGEBRA: R(a,b,c,d)=(b,c,d,a), P_x(R(...))=(x,b,c,d). Native tests must check both intervening formatters and the exit.',flush=True)
