#!/usr/bin/env python3
"""Local contracts for masked U control and the upper-addition producer.

No universal keyboard scheduler or arithmetic absorption theorem is claimed.
The native test is responsible for inter-chip timing and numeric results.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop()
    assert answer==unsat,label

def gate(header,accepted):
    a=State('masked_gate_%02X'%header);p=base(a,0x9C)
    p.add(a.m[31]==header%16,a.m[34]==header//16)
    out=[];b=ex(a,0x9C,*keys('gate_keys_%02X'%header),emitted_outputs=out)
    prove(p,addr(b)==(0x9E if accepted else 0x9D),'exact 9C classification')
    prove(p,And(*[x==y for x,y in zip(out,a.m)]),'9C changes no outgoing tetras')
    print('PASS gate %02X -> %s'%(header,'accepted' if accepted else 'rejected'),flush=True)

def producer(start,opcode,markers,source,target,request):
    tag='masked_%s_%02X'%(start,opcode)
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==opcode%16,a.r[33]==opcode//16,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker',*markers) else pages[n][22]!=15)
    path=[];reads=[];writes=[]
    for step in range(80):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop()
        assert len(ips)==1,('unforced',path,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15]
        following=slots[(slots.index(start)+step+1)%15]
        path.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        if ip==0xEE:reads.append(here)
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip==0xE9:
            assert here==target
            prove(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact E9 copy')
            writes.append(here)
        elif ip==0xA3:
            assert here==request
            prove(p,And(out[28]==original[source][28],out[31]==opcode%16,out[34]==opcode//16,
                        *[out[j]==old[j] for j in range(42) if j not in (28,31,34)]),'exact request header')
            writes.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no other output change at '+path[-1])
        pages[here]=out
        if ip==0xA3:
            prove(p,addr(a)==0xD3,'returns to D3');break
    else:raise AssertionError('no bounded request')
    assert reads==[source] and writes==[target,request]
    if target=='V':prove(p,pages['V'][22]!=15,'the X copy removes V')
    print('PASS connected producer:',{'accepted9C':start,'opcode':'%02X'%opcode,
          'EE':source,'E9':target,'A3':request},flush=True)
    print('PATH',' -> '.join(path),flush=True)

if __name__=='__main__':
    for header,accepted in [(0x98,True),(0x36,False),(0x3F,True),
                            (0x10,False),(0x1F,True),(0x28,False)]:gate(header,accepted)
    producer('U',0x36,('T','V'),'X','V','control')
    producer('control',0x36,('T',),'W','X1','U')
    producer('control',0x10,('T',),'W','X1','U')
    formatter=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    formatter(9,0,source_slot='X',marker_slots=('marker','T'),target_by_class=['W']*6+['X']*3)
    print('LIMIT: 36 rejects the U gate; arbitrary surrounding scanner flags can '
          'still change the subsequent route. No universal arithmetic absorption, '
          'native entry, or clean exit is asserted here.',flush=True)
