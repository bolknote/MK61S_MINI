#!/usr/bin/env python3
"""Local native-ROM contracts behind the two-marker fifth-word reader.

Physical entry placement and the complete keyboard exit are checked by JS.
These connected suffixes allow arbitrary numeric data and per-tick keys.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
    print('PASS:',label,flush=True)

a=State('p8_decode');p=base(a,0xAB);p.add(a.r[32]==8,a.r[35]==6);b=a
for i,ip in enumerate([0xAB,0xAD,0xA6]):
    prove(p,address(b)==ip,'recall 68 reaches %02X'%ip)
    b=ex(b,ip,*keys('p8_decode_keys_'+str(i)))
prove(p,And(address(b)==1,b.s1==6,stack(b)[0]==0xA7,b.r[35]==8),
      '68 selects M1 load D6, register digit 8, return A7')

names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8']
seq=[0xD6,0xA7,0xE5,0xE5,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
pg=[State('p8_page_'+n).m for n in names]
a=State('p8_suffix');a.m=pg[0];p=base(a,0xD6)
p.add(stack(a)[0]==0xA7,stack(a)[1]==0xAC,
      pg[2][22]!=15,pg[3][22]!=15,pg[4][22]==15)
b=a;source=[pg[0][3*i] for i in range(12)]
for i,ip in enumerate(seq):
    prove(p,address(b)==ip,'P8 suffix %02X at %s'%(ip,names[i]))
    out=[];b=ex(b,ip,*keys('p8_suffix_keys_'+str(i)),serial_inputs=pg[i+1],emitted_outputs=out)
    if 7<=i<=10:
        incoming=source if i==7 else [pg[i-1][1+3*j] for j in range(12)]
        prove(p,And(*[out[1+3*j]==incoming[j] for j in range(12)],
                    *[b.r[3*j]==pg[i][1+3*j] for j in range(12)],
                    *[out[j]==pg[i][j] for j in range(42) if j%3!=1 or j>=37]),
              'exact 12-tetra swap at '+names[i]+'; a marker is allowed as data')
    else:
        prove(p,And(*[out[j]==pg[i][j] for j in range(42)]),'no writes at '+names[i])
    if i<7:
        prove(p,And(*[b.r[3*j]==source[j] for j in range(12)]),'full P8 payload retained')
prove(p,And(address(b)==0xAC,b.s1==0),'P8 push is finite and returns to AC')

a=State('p7_read_aa');p=base(a,0xAA);p.add(a.r[30]==0,a.r[33]==4)
b=ex(a,0xAA,*keys('p7_read_aa_keys'))
prove(p,And(address(b)==0xE5,b.s1==13,stack(b)[0]==0xAB,b.r[32]==0,b.r[35]==4),
      'store 40 selects the +3 M2 reader and register digit 0')
names=['Z','T','U','V','W','Q','P7','P8','P9','P10','marker']
seq=[0xE5,0xE5,0xE5,0xE5,0xE6,0xED,0xEE,0xAB,0xAD,0xA4]
pg=[State('p7_read_page_'+n).m for n in names]
a=State('p7_read_suffix');a.m=pg[0];p=base(a,0xE5)
p.add(a.s1==13,stack(a)[0]==0xAB,a.r[32]==0,a.r[35]==4,
      *[pg[i][22]!=15 for i in range(3)],pg[3][22]==15)
b=a
for i,ip in enumerate(seq):
    prove(p,address(b)==ip,'P7 reader %02X at %s'%(ip,names[i]))
    out=[];b=ex(b,ip,*keys('p7_read_keys_'+str(i)),serial_inputs=pg[i+1],emitted_outputs=out)
    prove(p,And(*[out[j]==pg[i][j] for j in range(42)]),'source path is read-only')
    if i>=6:
        prove(p,And(*[b.r[3*j]==pg[6][1+3*j] for j in range(12)]),'all 12 P7 tetras survive')
prove(p,And(address(b)==1,b.s1==4,stack(b)[0]==0xA5),'P7 reaches the existing D4 writer helper')
print('NOT a full keyboard theorem: entry alignment and marker erasure require the native composition tests.',flush=True)
