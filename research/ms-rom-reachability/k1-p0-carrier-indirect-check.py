#!/usr/bin/env python3
"""Conditional connected ROM contract for a one-register marker carrier.

NOT a keyboard reachability proof. Native code must create the declared
carrier in P0 and reach D6(U) with the indirect-0 or indirect-A entry fields.
The twelve X-source tetras, every other serial tetra and per-tick keys
remain arbitrary. No later next-IP condition is assumed.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
A=lambda a:[a.r[3*j] for j in range(12)]
same=lambda x,y:And(*[a==b for a,b in zip(x,y)])
tet=lambda s:[int(c,16) for c in reversed(s)]
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);result=p.check()
    assert result==unsat,(label,p.model() if result==sat else result)
    p.pop()

def check(carrier='0020F0100000'):
    indirect_a=carrier=='0040F0000000'
    turns,wait,normalized={'0020F0100000':(5,8,'007000000F00'),
                          '0010F7000000':(6,6,'0070000000F6'),
                          '0040F0000000':(3,3,'0070000F0000')}[carrier]
    index=10 if indirect_a else 0
    seq=[0xD6]+[ip for _ in range(turns) for ip in (0x2F,0x20)]+[0x2F,0x21]
    seq += [0x23,0x25] if indirect_a else [0x22,0x36,0x25]
    seq += [1]*wait+[2]*(11 if indirect_a else 1)+[3,4,0xBA,0xCB,0xDD,0xD4,0x26,0x28,0x7E,0x71,0xAA]
    seq += [0xE5]*3+[0xE6,0xED,0xEE,0xAB,0xAD,0xA4]
    seq += [1]*9+[2,3,4,0xBA,0xCB,0xDD,0xD4]
    names=[slots[(7+i)%15] for i in range(len(seq)+1)]
    pages=[State('carrier_pointer_page_'+str(i)).m for i in range(len(seq)+1)]
    a=State('carrier_pointer');a.m=pages[0];p=base(a,0xD6)
    p.add(a.r[29]==index+1,a.r[32]==index,a.r[35]==1,a.r[26]==15,a.s1==6,
          *[x==v for x,v in zip(stack(a),(0x2F,0xAC,0x9A))],
          *[pages[0][3*j]==v for j,v in enumerate(tet(carrier))])
    for i,ip in enumerate(seq):
        if ip in (1,0xE5):p.add(pages[i][22]==15 if names[i] in ('marker','Z','T') else pages[i][22]!=15)
    b=a;source=None;writes=[]
    for i,ip in enumerate(seq):
        label='%d %02X(%s)'%(i,ip,names[i])
        prove(p,address(b)==ip,label+' forced next IP')
        if ip==0xEE:
            assert names[i]=='X';source=[pages[i][1+3*j] for j in range(12)]
        out=[];b=ex(b,ip,*keys('carrier_keys_'+str(i)),serial_inputs=pages[i+1],emitted_outputs=out)
        if ip==0xD4:
            writes.append(names[i]);expected=tet(normalized) if source is None else source
            prove(p,And(*[out[3*j]==v for j,v in enumerate(expected)],
                        *[out[j]==pages[i][j] for j in range(42) if j%3!=0 or j>=36]),
                  label+' exact P0 numeric write, all other tetras unchanged')
        else:prove(p,same(out,pages[i]),label+' no ring writes')
        if ip==0x25:prove(p,And(same(A(b),tet(normalized)),b.s1==4,stack(b)[0]==0x26),label+' normalized carrier')
        if ip==0x71:prove(p,And(b.r[30]==0,b.r[33]==4),label+' reconstructed direct store 40')
        if source is not None and ip not in (0xDD,0xD4):prove(p,same(A(b),source),label+' source held')
    assert writes==['U','U'],writes
    prove(p,address(b)==0xA5,'finite A5 return')
    print('PASS:',len(seq),'connected commands; indirect index %X, D6(P0=%s) -> D4(P0=%s) -> EE(X arbitrary) -> D4(P0=X); all other M1/M2/M3 tetras held.'%(index,carrier,normalized))
    print('LIMIT: conditional native entry; making the carrier and the subsequent A5/formatter exit are separate obligations.')

if __name__=='__main__':
    check()
    check('0010F7000000')
    check('0040F0000000')
