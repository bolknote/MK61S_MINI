#!/usr/bin/env python3
"""Shifted IK1303 W/Q exchange and IK1302's conditional direct-W reader.

Exact local ROM contracts, not universal keyboard reachability or full K1.
"""
import runpy
from pathlib import Path
from z3 import And, BitVecVal, If, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('check_ik1303_u_reader.py')))
State,execute,base,keys=(q[n] for n in ('State','execute','base','keys'))
address,A,B,prove=(q[n] for n in ('address','A','B','prove'))

# The same read/buffer path with the marker in T. At 60 the true marker
# has already passed. 37 finds the false T, so the output pair is W/Q.
names=['Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T','U','V','W','Q','P7']
seq=[0x53,0x4F,0x41,0x43,0x4D,0x60]+[0x37]*6+[0x27,0x61,0x4E,0x2A]
pages=[State('shifted_q_page_'+str(i)+'_'+n).m for i,n in enumerate(names)]
pages[15]=pages[0]  # same circulating Q, untouched until the final exchange
a=State('shifted_q');a.m=pages[0];p=base(a,0x53)
p.add(a.l==1,a.s1==6,a.r[32]==5,a.r[35]==0,a.r[41]==5,
      *[pages[i][22]!=15 for i in range(6,11)],pages[11][22]==15,
      pages[12][31]==4)  # A3's submitted request in physical U
source=[pages[0][1+3*i] for i in range(12)];b=a
for i,ip in enumerate(seq):
    prove(p,address(b)==ip,'shifted path executes %02X at %s'%(ip,names[i]))
    out=[];b=execute(b,ip,*keys('shifted_q_keys_'+str(i)),
                    serial_inputs=pages[i+1],emitted_outputs=out)
    if i<=3 or i==13:
        prove(p,And(*[x==y for x,y in zip(A(b),source)]),'Q survives in A after %02X'%ip)
    if 4<=i<=12:
        prove(p,And(*[x==y for x,y in zip(B(b),source)]),'Q survives in B after %02X'%ip)
    if i in [14,15]:
        incoming=source if i==14 else [pages[14][1+3*j] for j in range(12)]
        prove(p,And(*[out[1+3*j]==incoming[j] for j in range(12)],
                    *[b.r[3*j]==pages[i][1+3*j] for j in range(12)],
                    *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
              '%02X: exact twelve-tetra exchange in %s, other lanes/service unchanged'%(ip,names[i]))
    elif ip==0x27:
        prove(p,And(out[31]==15,*[out[j]==pages[i][j] for j in range(42) if j!=31]),
              '27 replaces request digit 4 by F in U; no other output changes')
    else:
        prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),
              '%02X leaves the entire current ring page %s unchanged'%(ip,names[i]))
prove(p,address(b)==0x39,'W/Q exchange terminates at 39 on P7')

# This explains why moving the direct-store marker from Z to T introduced
# a data-dependent scanner ambiguity before AA, despite EE itself being safe.
q2=q['q2'];State2,ex2,base2,keys2=(q2[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
for high,target in [(0,0x9D),(9,0x9E)]:
    a=State2('scanner_control_'+str(high));p=base2(a,0x9C);p.add(a.m[34]==high)
    b=ex2(a,0x9C,*keys2('scanner_keys_'+str(high)))
    prove(p,address(b)==target,'9C with M34=%X always selects %02X, independent of all lower U tetras'%(high,target))

# Check AA's destination 1 variant and bind the source path to the shifted
# pages. No U/V/W numeric assumptions are needed inside this suffix.
a=State2('shifted_direct_aa');p=base2(a,0xAA);p.add(a.r[30]==1,a.r[33]==4)
b=ex2(a,0xAA,*keys2('shifted_direct_aa_keys'))
prove(p,And(address(b)==0xE5,b.s1==13,q['stack'](b)[0]==0xAB,b.r[32]==1,b.r[35]==4),
      'AA decodes store 41 with the same +3 M2 source selector')
names2=['Z','T','U','V','W','Q','P7','P8','P9'];seq2=[0xE5,0xE5,0xE6,0xED,0xEE,0xAB,0xAD,0xA4]
pg=[State2('direct_w_'+n).m for n in names2]
a=State2('direct_w');a.m=pg[0];p=base2(a,0xE5)
p.add(a.s1==13,q['stack'](a)[0]==0xAB,a.r[32]==1,a.r[35]==4,pg[0][22]!=15,pg[1][22]==15)
b=a
for i,ip in enumerate(seq2):
    prove(p,address(b)==ip,'direct W path executes %02X at %s'%(ip,names2[i]))
    out=[];b=ex2(b,ip,*keys2('direct_w_keys_'+str(i)),serial_inputs=pg[i+1],emitted_outputs=out)
    prove(p,And(*[out[j]==pg[i][j] for j in range(42)]),'direct %02X is read-only'%ip)
    if i>=4:
        prove(p,And(*[x==pg[4][1+3*j] for j,x in enumerate(A(b))]),'direct %02X retains full W'%ip)
prove(p,And(address(b)==1,b.s1==4,q['stack'](b)[0]==0xA5),'direct W selects the existing D4 writer helper')
print('NOT full K1: W/Q exchange clobbers U header; direct W requires correct scanner alignment before AA.',flush=True)
