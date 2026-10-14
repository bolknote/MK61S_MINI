#!/usr/bin/env python3
"""ENTER(W): all flags force E0 -> A7 and the visible four-word push.

This is a local ROM proof, not a guessed key sequence. The EE(W) entry
and its real return stack must be established by native keyboard tests.
No zero assumptions are made for R23/R26/R29 or other free registers.
"""
import runpy
from pathlib import Path
from z3 import And, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,ex,base,keys=(q[n] for n in (
    'State','execute_command','base_solver','arbitrary_keys'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
stack=lambda a:[ZeroExt(4,a.st[36+i])|(ZeroExt(4,a.st[39+i])<<4)
                for i in range(3)]
A=lambda a:[a.r[3*j] for j in range(12)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premises',label)
    p.push();p.add(~claim);result=p.check()
    assert result==unsat,(label,p.model() if result==sat else result)
    p.pop();print('PASS',label,flush=True)

# E0 does not even need the narrower states produced by the preceding EE.
# Base constrains the instruction address and legal one-bit hardware flags;
# every four-bit register, S1, return stack and per-tick key signal is free.
a=State('enter_any_e0');p=base(a,0xE0);out=[]
b=ex(a,0xE0,*keys('enter_any_e0_keys'),emitted_outputs=out)
prove(p,And(address(b)==0xA7,*[x==y for x,y in zip(A(b),A(a))],
            *[x==y for x,y in zip(out,a.m)]),
      'isolated E0 always selects A7, holds all 12 A tetras, writes no ring tetra')

# Current physical geometry: ENTER source W, then Q, P7, P8..marker.
# Only pages visited by the E5 scan are constrained. The V marker is
# present but never encountered before the scan reaches the real marker.
# The complete W, X, Y, Z, T payloads remain arbitrary twelve-tetra words.
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
seq=[0xEE,0xE0,0xA7]+[0xE5]*4+[
    0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9]
names=[slots[(9+i)%15] for i in range(len(seq)+1)]
pages={n:State('enter_whole_'+n).m for n in slots}
a=State('enter_whole');a.m=pages['W'];p=base(a,0xEE)
p.add(a.s1==13,*[x==v for x,v in zip(stack(a),[0xE0,0x8E,0x9A])],
      pages['V'][22]==15,pages['marker'][22]==15,
      *[pages[n][22]!=15 for n in ['P8','P9','P10']])

b=a;carried=[pages['W'][1+3*j] for j in range(12)]
written=[];before_a9=None
for i,ip in enumerate(seq):
    n=names[i];label='%02X(%s)'%(ip,n)
    prove(p,address(b)==ip,label+' forced connected address')
    if ip==0xA9:
        before_a9=b
        prove(p,And(*[x==pages['T'][1+3*j] for j,x in enumerate(A(b))]),
              'the complete old T is displaced into A before A9')
    out=[]
    b=ex(b,ip,*keys('enter_whole_keys_'+str(i)),
         serial_inputs=pages[names[i+1]],emitted_outputs=out)
    if ip in (0xE7,0xA8):
        prove(p,And(*[out[1+3*j]==carried[j] for j in range(12)],
                    *[out[j]==pages[n][j] for j in range(42)
                      if j%3!=1 or j>=37]),
              label+' exact twelve-tetra copy; all other lanes/service held')
        written.append(n);carried=[pages[n][1+3*j] for j in range(12)]
    else:
        prove(p,And(*[x==y for x,y in zip(out,pages[n])]),
              label+' does not write the ring')
    if ip!=0xA9:
        prove(p,And(*[x==y for x,y in zip(A(b),carried)]),
              label+' full carried word survives')
assert written==['X','Y','Z','T'] and before_a9 is not None
prove(p,And(address(b)==0xE1,b.s1==0,
            *[b.r[3*j]==pages['T'][1+3*j] for j in range(10)],
            b.r[30]==before_a9.r[32],b.r[33]==before_a9.r[35]),
      'A9 returns E1; ten displaced T tetras remain and its high exponent fields are replaced')
print('RESULT: ENTER(W) unavoidably writes W->X, old X->Y, old Y->Z, old Z->T; '
      '48 exact numeric writes. All initial R23/R26/R29 values are covered.',flush=True)
print('LIMIT: conditional EE(W) keyboard entry and primary path only; not a global '
      'impossibility proof, secondary-chip audit, or proof of every later return.',flush=True)
