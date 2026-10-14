#!/usr/bin/env python3
"""Why equal-operand subtraction supplies the missing T reserve.

Exact local ROM contracts, not a universal keyboard/numeric theorem.
"""
import runpy
from pathlib import Path
from z3 import And, If, Or, UGE, ULE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop();assert answer==unsat,label

def subtract():
    q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
    S,ex,base,keys,addr=(q[n] for n in ('State','ex','base','keys','address'))
    pages={n:S('equal_sub_'+n).m for n in slots};original=dict(pages)
    a=S('equal_sub');a.m=pages['marker'];p=base(a,0x6E)
    p.add(a.r[29]==0,pages['control'][31]==1,pages['control'][34]==1,
          a.st[36]==10,a.st[39]==3,a.st[37]==10,a.st[40]==3)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z') else pages[n][22]!=15)
    u=[pages['X'][1+3*j] for j in range(12)]
    p.add(*[pages['Y'][1+3*j]==v for j,v in enumerate(u)])
    for j in [*range(8),9,10]:p.add(ULE(u[j],9))
    p.add(UGE(u[7],1),UGE(u[0],1),u[8]==9,u[11]==9,Or(u[9]!=0,u[10]!=0))
    expected=[('X',None),('Y','Z'),('Z','T'),('T','T')]
    route=[];writes=[];acks=[]
    for step in range(160):
        p.push();ips=q['q']['possible_values'](addr(a),p,257);p.pop()
        assert len(ips)==1,('unforced subtraction',route,ips)
        ip=ips[0];here=slots[step%15];following=slots[(step+1)%15];old=pages[here]
        route.append('%02X(%s)'%(ip,here));out=[]
        a=ex(a,ip,*keys('equal_sub_'+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip in (0x3A,0x2A):
            target,source=expected[len(writes)];assert here==target
            value=[0]*12 if source is None else [original[source][1+3*j] for j in range(12)]
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(value)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact subtraction output '+here)
            writes.append((target,source))
        elif ip==0x27:
            assert here=='control'
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only ACK')
            acks.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no other ring write '+route[-1])
        pages[here]=out
        if ip==0x39:
            prove(p,And(addr(a)==0x6E,a.r[29]==0),'quiet return');break
    else:raise AssertionError('no bounded subtraction return')
    assert writes==expected and acks==['control','control']
    for n in slots:prove(p,pages[n][22]==15 if n in ('marker','Y') else pages[n][22]!=15,'post-sub marker '+n)
    print('PASS equal negative-exponent class-0 operands: X=0, Y=oldZ, Z=T=oldT; all other tetras held except ACK.',flush=True)
    print('PATH',' -> '.join(route),flush=True)

def nop():
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    S,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    pages={n:S('y_nop_'+n).m for n in slots};a=S('y_nop');a.m=pages['Z'];p=base(a,0x9C)
    p.add(a.r[30]==4,a.r[33]==5,a.r[23]==0,a.r[26]==0,a.r[29]==4)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Y') else pages[n][22]!=15)
    for n in ('Z','control'):p.add(If(pages[n][31]==15,UGE(pages[n][34],1),UGE(pages[n][34],7)))
    reads=[];gates=[];route=[]
    for step in range(100):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop();assert len(ips)==1,(route,ips)
        ip=ips[0];here=slots[(5+step)%15];old=pages[here];following=slots[(6+step)%15]
        route.append('%02X(%s)'%(ip,here))
        if ip==0x9C:gates.append(here)
        if ip==0xEE:
            reads.append(here)
            if len(reads)==2:
                assert gates==['Z','control'] and reads==['X','X']
                prove(p,And(a.st[36]==3,a.st[39]==14),'late E3')
                print('PASS NOP at Z, only extra Y: reads X twice, no early writes.',flush=True)
                print('PATH',' -> '.join(route),flush=True);return
        out=[];a=ex(a,ip,*keys('y_nop_'+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        prove(p,And(*[x==y for x,y in zip(out,old)]),'no NOP write '+route[-1]);pages[here]=out
    raise AssertionError('no bounded NOP reader')

if __name__=='__main__':
    subtract();nop()
    producer=runpy.run_path(str(root/'k1-y-t-rotate-path-check.py'))['next_request']
    for code in (0x25,0x11):producer('T',code)
    secondary=runpy.run_path(str(root/'k1-z-reserve-rotate-path-check.py'))['secondary']
    secondary('marker');secondary('Y')
    fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    for z in (0,1):fmt(9,z,source_slot='X',marker_slots=('marker','Y'),target_by_class=['U']*9)
    fmt(0,7,True,True,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    print('LIMIT: local accepted contracts. Inter-chip scheduling and keyboard prefix need the native audit.',flush=True)
