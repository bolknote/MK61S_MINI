#!/usr/bin/env python3
"""Connected RCL0 through real/Y/T/V, and ENTER through real/Y.

Local ROM contracts; native reachability and concurrent writes are separate.
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
    p.push();p.add(~claim);answer=p.check();p.pop();assert answer==unsat,label

def read(start,code,extra):
    tag='ytv_read_%02x_'%code+start
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==code%16,a.r[33]==code//16,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    if code==0x0E:p.add(a.s1==14)
    if code==0x60:p.add(pages['U'][21]!=15)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker',*extra) else pages[n][22]!=15)
    path=[];reads=[];writes=[];source=None;carried=None
    for step in range(150):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop()
        assert len(ips)==1,('unforced reader',path,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];following=slots[(slots.index(start)+step+1)%15]
        path.append('%02X(%s)'%(ip,here));old=pages[here]
        if ip==0xEE:
            reads.append(here)
            if len(reads)==2:
                assert here=='X' and writes==['X','Y','Z','T'],(reads,writes)
                prove(p,And(a.st[36]==3,a.st[39]==14),'late E3 return')
                for n,word in [('X',source),('Y',original['X']),('Z',original['Y']),('T',original['Z'])]:
                    offset=0 if n=='X' and code==0x60 else 1
                    prove(p,And(*[pages[n][1+3*j]==word[offset+3*j] for j in range(12)]),'exact output '+n)
                for n in slots:
                    if n not in writes:prove(p,And(*[x==y for x,y in zip(pages[n],original[n])]),'untouched '+n)
                print('PASS',{'code':'%02X'%code,'start':start,'markers':extra,'reads':reads,'writes':writes},flush=True)
                print('PATH',' -> '.join(path),flush=True);return
            if code==0x0E:
                assert here==('U' if start=='control' else 'X'),path
                source=original[here];carried=[old[1+3*j] for j in range(12)]
        out=[];a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip==0xD6:
            assert here=='U' and code==0x60
            source=original['U'];carried=[old[3*j] for j in range(12)]
        if ip in (0xE7,0xA8):
            assert carried is not None
            prove(p,And(*[out[1+3*j]==carried[j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact push '+here)
            carried=[old[1+3*j] for j in range(12)];writes.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no extra write '+path[-1])
        pages[here]=out
    raise AssertionError('no bounded late read')

if __name__=='__main__':
    # Only the real-control RCL0 origin is claimed. Additional hidden V
    # changes register addressing for other origins; do not extrapolate.
    read('control',0x60,('Y','T','V'))
    for start in ('control','Z'):read(start,0x0E,('Y',))
    formatter=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    for zeroes in (0,1):formatter(9,zeroes,source_slot='X',marker_slots=('marker','Z','V'),target_by_class=['V']*9)
    formatter(9,0,source_slot='X',marker_slots=('marker','Z'),target_by_class=['V']*9)
    print('LIMIT: conditional primary paths/formatter classes only; no keyboard or full-K1 theorem.',flush=True)
