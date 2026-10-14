#!/usr/bin/env python3
"""Buffer preparation and numeric output of IK1303's four-word rotation.

Native tests establish the D4 entry, C=P7 and B=P8. The connected D4..61
path captures P9/P10, then 3A*3/2A writes the permutation. The source
tetras are arbitrary, including nondecimal digits; this is not a safe
keyboard-return theorem.
"""
import runpy
from pathlib import Path
from z3 import And
q=runpy.run_path(str(Path(__file__).with_name('check_ik1303_u_reader.py')))
State,ex,base,keys,address,prove,stack=(q[n] for n in ('State','execute','base','keys','address','prove','stack'))

# At D4 entry, C already contains P7 and B contains P8. Five reads capture
# the remaining two words; the connected path arranges ST and restores P7
# to A. C's R29/R32/R35 are PAYLOAD, not fixed opcode fields at this point.
pre_names=['Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T','U','V','W','Q','P7']
pre_seq=[0xD4]*5+[0xC4,0x2C,0x3B,0x2B,0x60]+[0x37]*4+[0x27,0x61]
pre_pages={n:State('rotate_buffer_page_'+n).m for n in set(pre_names)}
a=State('rotate_buffer');a.m=pre_pages['Q'];p=base(a,0xD4)
p.add(a.l==1,a.s1==9,a.r[37]==4,a.r[38]==0,a.r[40]==13,a.r[41]==6,
      *[x==v for x,v in zip(stack(a),[0x29,0x3A,0x3A])],
      *[a.r[2+3*i]==pre_pages['P7'][1+3*i] for i in range(12)],
      *[a.r[1+3*i]==pre_pages['P8'][1+3*i] for i in range(12)],
      *[pre_pages[n][22]!=15 for n in ['Z','T','U']],
      pre_pages['V'][22]==15,pre_pages['W'][31]==15)
b=a
for i,ip in enumerate(pre_seq):
    prove(p,address(b)==ip,'buffer path executes %02X at %s'%(ip,pre_names[i]))
    out=[];b=ex(b,ip,*keys('rotate_buffer_keys_'+str(i)),
                serial_inputs=pre_pages[pre_names[i+1]],emitted_outputs=out)
    # The already acknowledged W:2F remains F under the second 27.
    prove(p,And(*[out[j]==pre_pages[pre_names[i]][j] for j in range(42)]),
          'buffer path leaves the ring unchanged at '+pre_names[i])
prove(p,And(address(b)==0x3A,b.s1==5,
            *[b.r[3*i]==pre_pages['P7'][1+3*i] for i in range(12)],
            *[b.st[3*i+lane]==pre_pages[n][1+3*i]
              for lane,n in enumerate(['P8','P9','P10']) for i in range(12)]),
      'connected D4..61 prepares all four arbitrary words and the exact 3A output selector')

names=['P7','P8','P9','P10','marker']
pages=[State('rotate_page_'+name).m for name in names]
a=State('rotate_output');a.m=pages[0];p=base(a,0x3A);p.add(a.s1==5)
for i in range(12):
    p.add(a.r[3*i]==pages[0][1+3*i])
    for lane in range(3):p.add(a.st[3*i+lane]==pages[lane+1][1+3*i])
b=a
for n,ip in enumerate([0x3A,0x3A,0x3A,0x2A]):
    prove(p,address(b)==ip,'rotation executes %02X at %s'%(ip,names[n]))
    out=[];b=ex(b,ip,*keys('rotate_keys_'+str(n)),serial_inputs=pages[n+1],emitted_outputs=out)
    source=pages[(n+1)%4]
    prove(p,And(*[out[1+3*i]==source[1+3*i] for i in range(12)],
                *[out[i]==pages[n][i] for i in range(42) if i%3!=1 or i>=37]),
          'exact next-word copy at '+names[n]+'; M1/M3/service unchanged')
prove(p,address(b)==0x39,'four-word rotation stops at 39 on the real marker')
print('LOCAL CONTRACT: native tests supply the D4 entry fields; no safe repeated keyboard readout/return is proved.',flush=True)
