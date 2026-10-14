#!/usr/bin/env python3
"""Fixed-number formatter cannot be retimed by hidden display/mode flags.

The sole formatter call-context premise is ST top E3 at EE. In particular
S1, R38, R41 and every other entry register are arbitrary, as are keyboard
signals at every tick. Numeric source and physical marker layout are fixed.
This is not a keyboard reachability proof for a different source/call site.
"""
import os
import runpy
from pathlib import Path
from z3 import And, Or, UGE, ULE, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);result=p.check()
    assert result==unsat,(label,p.model() if result==sat else result)
    p.pop()

def check(header,z,small=False,zero=False):
    tag='k1_format_%d_%d_%d_%d'%(header,z,small,zero)
    a=State(tag);p=base(a,0xEE);p.add(a.st[36]==3,a.st[39]==14)
    source=[a.m[1+3*j] for j in range(12)]
    if zero:p.add(*[v==0 for v in source])
    else:
        for i in list(range(8))+[9,10]:p.add(ULE(source[i],9))
        p.add(UGE(source[7],1),Or(source[8]==0,source[8]==9),source[11]==header,
              *[source[j]==0 for j in range(z)])
        if small:p.add(source[10]==0,ULE(source[9],7-z),Or(source[z]!=0,source[9]==7-z))
        else:
            p.add(source[z]!=0)
            if header==9:p.add(Or(source[9]!=0,source[10]!=0))
            else:p.add(Or(source[10]!=0,UGE(source[9],8)))
    seq=[int(x,16) for x in 'EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE'.split()]
    seq += [0xD9] if header==9 else ([0xD0,0xF2] if small else [0xD0])
    seq += [ip for _ in range(z+1) for ip in (0xF3,0xF7,0xF1)]
    seq += [ip for _ in range(8-z) for ip in (0xF4,0xF6)]+[0xF4,0xEA,0xEC]
    b=a
    for i,ip in enumerate(seq):
        label=tag+' step %d %02X'%(i,ip);prove(p,address(b)==ip,label+' fixed address')
        old=b.m;out=[];b=ex(b,ip,*keys(label),emitted_outputs=out)
        prove(p,And(*[x==y for x,y in zip(out,old)]),label+' no ring writes')
    prove(p,And(address(b)==0x40,*[b.r[3*j]==source[j] for j in range(12)]),tag+' exact number and 40 return')
    assert len(seq)==39+z+int(small)
    if zero:assert len(seq)==47
    targets={}
    for origin in ('X','X1'):
        p.push();state=b;first=(slots.index(origin)+len(seq))%15
        form=[0x40,0x41,0x43 if zero else 0x42,0x46]
        while slots[(first+len(form))%15] not in ('marker','Z'):form.append(0xE5)
        form += [0xE5,0xE6,0xE8,0xE7]
        for j,ip in enumerate(form):
            where=slots[(first+j)%15];label=tag+' '+origin+' %02X(%s)'%(ip,where)
            if ip==0xE5:p.add(state.m[22]==15 if where in ('marker','Z') else state.m[22]!=15)
            prove(p,address(state)==ip,label+' fixed address')
            old=state.m;out=[];state=ex(state,ip,*keys(label),emitted_outputs=out)
            if ip==0xE7:
                prove(p,And(*[out[1+3*k]==source[k] for k in range(12)],
                            *[out[k]==old[k] for k in range(42) if k%3!=1 or k>=37]),label+' exact sole twelve-tetra write')
            else:prove(p,And(*[x==y for x,y in zip(out,old)],*[state.r[3*k]==source[k] for k in range(12)]),label+' number held, no writes')
        prove(p,address(state)==0x47,tag+' '+origin+' final 47')
        target=slots[(first+len(form)-1)%15];qvalue=z+int(small)
        expected=('V' if qvalue<=4 else 'X') if origin=='X' else ('V' if 1<=qvalue<=5 else 'X')
        assert target==expected;targets[origin]=target;p.pop()
    print('PASS:',{'header':header,'suppressedZeros':z,'decimal':small,'zero':zero,
                   'commands':len(seq),'targets':targets,'entryModes':'all arbitrary except ST top E3'},flush=True)

if __name__=='__main__':
    only=os.environ.get('K1_FORMAT_ONLY')
    for header in (9,0):
        for small in ([False] if header==9 else [False,True]):
            for z in range(8):
                if only and only!='%d,%d,%d'%(header,z,small):continue
                check(header,z,small)
    if not only:check(0,7,True,True)
    print('LIMIT: fixed EE source, ST top E3 and marker geometry; another return stack, moving data/markers, or another native entry is not excluded.',flush=True)
