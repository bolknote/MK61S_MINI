#!/usr/bin/env python3
"""Exact IK1303 numeric P7/P8 exchange after an internal V marker.

Native tests establish the keyboard placement and entry fields. This
connected suffix admits arbitrary payloads, unrelated state and keys.
"""
import runpy
from pathlib import Path
from z3 import And
q=runpy.run_path(str(Path(__file__).with_name('check_ik1303_u_reader.py')))
State,ex,base,keys,A,B,address,prove=(q[n] for n in ('State','execute','base','keys','A','B','address','prove'))
names=['P8','P9','P10','marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9']
seq=[0x53,0x4F,0x41,0x43,0x4D,0x60]+[0x37]*6+[0x27,0x61,0x4E,0x2A]
pages=[State('upper_swap_page_'+str(i)+'_'+n).m for i,n in enumerate(names)]
pages[15]=pages[0]
a=State('upper_swap');a.m=pages[0];p=base(a,0x53)
p.add(a.l==1,a.s1==6,a.r[32]==5,a.r[35]==0,a.r[41]==5,
      *[pages[i][22]!=15 for i in range(6,11)],pages[11][22]==15,pages[12][31]==4)
source=[a.m[1+3*i] for i in range(12)];b=a
for i,ip in enumerate(seq):
    prove(p,address(b)==ip,'upper path executes %02X at %s'%(ip,names[i]))
    out=[];b=ex(b,ip,*keys('upper_swap_keys_'+str(i)),serial_inputs=pages[i+1],emitted_outputs=out)
    if i<=3 or i==13:prove(p,And(*[x==y for x,y in zip(A(b),source)]),'full P8 retained in A')
    if 4<=i<=12:prove(p,And(*[x==y for x,y in zip(B(b),source)]),'full P8 retained in B')
    if i in (14,15):
        incoming=source if i==14 else [pages[14][1+3*j] for j in range(12)]
        prove(p,And(*[out[1+3*j]==incoming[j] for j in range(12)],
                    *[b.r[3*j]==pages[i][1+3*j] for j in range(12)],
                    *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
              'exact numeric exchange at '+names[i]+'; service/M1/M3 preserved')
    elif ip==0x27:
        prove(p,And(out[31]==15,*[out[j]==pages[i][j] for j in range(42) if j!=31]),
              'response changes only W M31 from request 4 to F')
    else:prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),'no other ring writes at '+names[i])
prove(p,address(b)==0x39,'P7/P8 pair terminates at 39 on P9')
print('NOT an intact-Ms operation: V remains a marker and the primary request clobbers three W header tetras.',flush=True)
