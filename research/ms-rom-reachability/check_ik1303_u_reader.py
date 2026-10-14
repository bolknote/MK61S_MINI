#!/usr/bin/env python3
"""Exact, connected IK1303 U -> A -> B -> A -> X data channel.

This changes only the symbolic interpreter's selected ROM tables. The native
reference and its live chip state are not edited. All source U tetras,
unrelated state, per-tick keyboard signals and incoming pages stay symbolic.
"""
import json
import runpy
import subprocess
from pathlib import Path
from z3 import And, Or, If, BitVecVal, ZeroExt, sat, unsat

q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
rom=json.loads(subprocess.check_output(['node','-e',
    'console.log(JSON.stringify(require(process.argv[1])["ИК1303"]))',str(q['ROM_PATH'])],text=True))
q['execute_command'].__globals__.update(COMMANDS=rom['команды'],
    SYNCS=rom['синхропрограммы'],MICROS=rom['микрокоманды'])
State,execute,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])
stack=lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
A=lambda a:[a.r[3*i] for i in range(12)]
B=lambda a:[a.r[1+3*i] for i in range(12)]

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);assert p.check()==unsat,label;p.pop()
    print('PASS:',label,flush=True)

# Primary-chip request producer. Its A2 search stops at the false X marker
# and A3 writes user opcode 14 into the next physical word Y. IK1303 reads
# that word one macro later; it is not a host-injected dispatch field.
q2=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
a=q2['State']('ik02_swap_request');p=q2['base_solver'](a,0xA2)
p.add(a.m[22]==15,a.r[32]==4,a.r[35]==1,a.r[37]==3,a.r[40]==13)
request_page=q2['State']('ik02_swap_request_y').m;out=[]
b=q2['execute_command'](a,0xA2,*q2['arbitrary_keys']('ik02_swap_request_keys'),
                        serial_inputs=request_page,emitted_outputs=out)
prove(p,And(address(b)==0xA3,b.r[30]==4,b.r[33]==1,b.r[27]==a.r[27],
            *[out[j]==a.m[j] for j in range(42)]),
      'IK1302 A2 recognizes the X marker and prepares request 14 without memory writes')
out=[];b=q2['execute_command'](b,0xA3,*q2['arbitrary_keys']('ik02_swap_submit_keys'),emitted_outputs=out)
prove(p,And(address(b)==0xD3,out[28]==a.r[27],out[31]==4,out[34]==1,
            *[out[j]==request_page[j] for j in range(42) if j not in [28,31,34]]),
      'IK1302 A3 writes only request 14 plus old R27 into the following word and returns to D3')

# How the false X marker and the ordinary 14 request create the five source
# fields. The next research step removes unnecessary zero-page restrictions:
# neither the request's third tetra nor either intervening word matters.
pre_names=['X','Y','Z','T','U']
pre_pages=[State('ik03_reader_prefix_'+name).m for name in pre_names]
pre=State('ik03_reader_prefix');pre.m=pre_pages[0];p=base(pre,0x6E)
p.add(pre.r[29]==0,pre_pages[0][22]==15,
      pre_pages[1][34]==1,pre_pages[1][31]==4)
b=pre
for i,ip in enumerate([0x6E,0x5E,0x50,0x52]):
    prove(p,address(b)==ip,'false-marker prefix executes %02X at %s'%(ip,pre_names[i]))
    out=[];b=execute(b,ip,*keys('ik03_reader_prefix_keys_%d'%i),
                    serial_inputs=pre_pages[i+1],emitted_outputs=out)
    prove(p,And(*[out[j]==pre_pages[i][j] for j in range(42)]),
          'prefix %02X does not change the ring'%ip)
prove(p,And(address(b)==0x53,b.l==1,b.s1==6,b.r[32]==5,b.r[35]==0,b.r[41]==5),
      'marker + request 14 construct ALL five reader entry fields; two intervening words and request low tetra are arbitrary')

# Native source 53 at U: these five control fields are asserted by the
# keyboard tests for every case. No source digit is constrained here.
names=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z']
seq=[0x53,0x4F,0x41,0x43,0x4D,0x60,0x37,0x37,0x37,0x27,0x61,0x4E,0x2A]
pages=[State('ik03_reader_page_'+name).m for name in names]
a=State('ik03_reader');a.m=pages[0];p=base(a,0x53)
p.add(a.l==1,a.s1==6,a.r[32]==5,a.r[35]==0,a.r[41]==5,
      pages[6][22]!=15,pages[7][22]!=15,pages[8][22]==15)
b=a;source=[a.m[1+3*i] for i in range(12)]
for i,ip in enumerate(seq):
    prove(p,address(b)==ip,'IK1303 executes %02X at physical %s'%(ip,names[i]))
    out=[];b=execute(b,ip,*keys('ik03_reader_keys_%d'%i),
                    serial_inputs=pages[i+1],emitted_outputs=out)
    if i<=3 or i==10:
        prove(p,And(*[x==y for x,y in zip(A(b),source)]),
              '%02X retains every original U tetra in A'%ip)
    if 4<=i<=9:
        prove(p,And(*[x==y for x,y in zip(B(b),source)]),
              '%02X retains every original U tetra in B, including sign and exponent'%ip)
    if i==11:
        incoming=source
    elif i==12:
        incoming=[pages[11][1+3*j] for j in range(12)]
    else:
        incoming=None
    if incoming is not None:
        prove(p,And(*[out[1+3*j]==incoming[j] for j in range(12)],
                    *[b.r[3*j]==pages[i][1+3*j] for j in range(12)],
                    *[out[j]==pages[i][j] for j in range(42) if j%3!=1 or j>=37]),
              '%02X exchanges exactly twelve numeric tetras at %s; M1/M3/service unchanged'%(ip,names[i]))
    elif ip==0x27:
        prove(p,And(*[out[j]==pages[i][j] for j in range(42) if j!=31]),
              '27 can change only the true control nibble M31, not any Ms word')
    else:
        prove(p,And(*[out[j]==pages[i][j] for j in range(42)]),
              '%02X does not write its current ring page %s'%(ip,names[i]))
prove(p,address(b)==0x39,'the two-word output finishes at 39, not in a repeating swap block')

# Generalize the marker-wait portion beyond the three iterations above.
a=State('ik03_reader_wait');p=base(a,0x37);out=[]
b=execute(a,0x37,*keys('ik03_reader_wait_keys'),emitted_outputs=out)
prove(p,And(address(b)==If(a.m[22]==15,BitVecVal(0x27,8),BitVecVal(0x37,8)),
            *[x==y for x,y in zip(B(b),B(a))],
            *[x==y for x,y in zip(stack(b),stack(a))],
            *[out[j]==a.m[j] for j in range(42)]),
      'any number of 37 waits preserves the complete U buffer and return stack without memory writes')

print('NOT a universal keyboard theorem: native tests supply the false-X/request context, R29=0 and the real-marker alignment. Zero Z/T are NOT needed inside this prefix.',flush=True)
