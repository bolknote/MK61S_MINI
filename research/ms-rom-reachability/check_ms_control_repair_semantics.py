#!/usr/bin/env python3
"""Local control-payload and ACK contracts; not keyboard reachability.

Different payloads share the 1F request byte and every nonnumeric field.
The primary result is full chip-state noninterference. The secondary
result explicitly retains one dependent tetra R23 rather than silently
declaring it harmless. IK1306 and normal exit are separate obligations.
"""
import runpy
from pathlib import Path
from z3 import And, BitVec, Or, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop();print('PASS:',label,flush=True)

def equal_state(a,b):
    return And(*[x==y for attr in ('r','m','st') for x,y in zip(getattr(a,attr),getattr(b,attr))],
               *[getattr(a,n)==getattr(b,n) for n in ('s','s1','l','t','carry')])

State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
a=State('primary_control_payload');p=base(a,0x9C);p.add(a.m[34]==1,a.m[31]==15)
b=a.copy()
for j in range(10):b.m[1+3*j]=BitVec('primary_other_payload_'+str(j),4)
signals=keys('primary_common_keys');incoming=State('primary_next_page').m
aa=ex(a,0x9C,*signals,serial_inputs=incoming)
bb=ex(b,0x9C,*signals,serial_inputs=incoming)
prove(p,And(address(aa)==0x9E,address(bb)==0x9E),'IK1302 9C accepts 1F with arbitrary payload')
prove(p,equal_state(aa,bb),'IK1302 complete state after 9C is independent of the ten control payload tetras')

sec=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
State,ex,base,keys=(sec[n] for n in ('State','ex','base','keys'))
pages=[State('secondary_page_'+str(i)).m for i in range(4)]
other=list(pages[1])
for j in range(10):other[1+3*j]=BitVec('secondary_other_payload_'+str(j),4)
a=State('secondary_control_payload');a.m=pages[0];b=a.copy();p=base(a,0x6E)
p.add(a.r[29]==0,pages[0][22]==15,pages[1][34]==1,pages[1][31]==15)
for i,ip in enumerate((0x6E,0x5E,0x39)):
    prove(p,And(address(a)==ip,address(b)==ip),'IK1303 %02X fixed in 1F dispatch'%ip)
    signals=keys('secondary_common_keys_'+str(i));oa=[];ob=[]
    pa=pages[i+1];pb=other if i==0 else pa
    old_a,old_b=a.m,b.m
    a=ex(a,ip,*signals,serial_inputs=pa,emitted_outputs=oa)
    b=ex(b,ip,*signals,serial_inputs=pb,emitted_outputs=ob)
    prove(p,And(*[x==y for x,y in zip(oa,old_a)],*[x==y for x,y in zip(ob,old_b)]),
          'IK1303 %02X preserves every ring tetra'%ip)
prove(p,And(address(a)==0x6E,a.r[29]==0),'IK1303 1F dispatch returns to marker scan')
dependent=[]
for attr in ('r','m','st'):
    for i,(x,y) in enumerate(zip(getattr(a,attr),getattr(b,attr))):
        p.push();p.add(x!=y)
        if p.check()==sat:dependent.append('%s[%d]'%(attr,i))
        p.pop()
for attr in ('s','s1','l','t','carry'):
    p.push();p.add(getattr(a,attr)!=getattr(b,attr))
    if p.check()==sat:dependent.append(attr)
    p.pop()
print('SECONDARY PAYLOAD DEPENDENCE after quiet return:',dependent,flush=True)
assert dependent==['r[23]']
# The one retained tetra has to be followed, not dismissed as harmless.
for i in range(12):
    ip=0x6E
    prove(p,And(address(a)==ip,address(b)==ip),'unmarked scan %d stays at 6E'%i)
    p.add(a.m[22]!=15,b.m[22]!=15)
    incoming=State('quiet_scan_page_'+str(i)).m
    signals=keys('quiet_scan_keys_'+str(i))
    a=ex(a,ip,*signals,serial_inputs=incoming)
    b=ex(b,ip,*signals,serial_inputs=incoming)
    p.push();p.add(~equal_state(a,b));same=p.check()==unsat;p.pop()
    if same:
        print('PASS: complete secondary state forgets control payload after',i+1,'unmarked 6E commands',flush=True)
        break
else:
    print('LIMIT: residual secondary R23 survives twelve unmarked scans; no global dead-payload claim.',flush=True)

a=State('secondary_ack');p=base(a,0x27);out=[]
p.add(a.m[34]==1)
b=ex(a,0x27,*keys('secondary_ack_keys'),emitted_outputs=out)
prove(p,And(out[34]==1,out[31]==15,*[out[i]==a.m[i] for i in range(42) if i not in (31,34)]),
      'IK1303 27 turns an existing 1x request into 1F, changing only M31 and preserving forty-one tetras')
print('LIMIT: these local contracts do not cover IK1306, keyboard entry, removal of W, or every future use of the physical control word.',flush=True)
