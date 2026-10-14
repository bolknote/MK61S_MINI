#!/usr/bin/env python3
"""Connected local producer/consumer for reserving V after Y/T preparation.

No native state injection or keyboard search. The two chips are proved as
local paths; their actual scheduling is a separate native-test obligation.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']


def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check()
    assert answer==unsat,(label,p.model() if answer==sat else answer)
    p.pop()


def primary(opcode=0x14):
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    pages={n:State('yt_swap_primary_'+n).m for n in slots};original=dict(pages)
    a=State('yt_swap_primary');a.m=pages['control'];p=base(a,0x9C)
    p.add(a.r[30]==opcode%16,a.r[33]==opcode//16,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Y','T') else pages[n][22]!=15)
    route=[];writes=[];reads=[]
    for step in range(80):
        p.push();ips=q['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(1+step)%15];nxt=slots[(2+step)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        if ip==0xEE:reads.append(here)
        a=ex(a,ip,*keys('yt_swap_primary_'+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip==0xE9:
            assert here=='X1'
            prove(p,And(*[out[1+3*j]==original['W'][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'reserve W in X1')
            writes.append(('E9',here))
        elif ip==0xA3:
            assert here=='Z'
            prove(p,And(out[28]==original['W'][28],out[31]==opcode%16,out[34]==opcode//16,
                        *[out[j]==old[j] for j in range(42) if j not in (28,31,34)],
                        address(a)==0xD3),'only request%02X in Z'%opcode)
            writes.append(('A3',here))
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no other primary write '+route[-1])
        pages[here]=out
        if ip==0xA3:break
    else:raise AssertionError('unclosed request path')
    assert reads==['W'] and writes==[('E9','X1'),('A3','Z')]
    print('PASS primary:', ' -> '.join(route),flush=True)
    print('RESULT: W -> X1 before request%02X overwrites only three Z header tetras; Ms unchanged.'%opcode,flush=True)


def secondary():
    q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
    State,ex,base,keys,address=(q[n] for n in ('State','ex','base','keys','address'))
    pages={n:State('yt_swap_secondary_'+n).m for n in slots};original=dict(pages)
    a=State('yt_swap_secondary');a.m=pages['Y'];p=base(a,0x6E)
    p.add(a.r[29]==0,pages['Z'][34]==1,pages['Z'][31]==4)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Y','T') else pages[n][22]!=15)
    route=[];writes=[]
    for step in range(80):
        p.push();ips=q['q']['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(4+step)%15];nxt=slots[(5+step)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        a=ex(a,ip,*keys('yt_swap_secondary_'+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip in (0x4E,0x2A):
            target,source=('X','V') if ip==0x4E else ('Y','X')
            assert here==target
            prove(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact '+source+' -> '+target)
            writes.append((target,source))
        elif ip==0x27:
            assert here=='control'
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only control ACK')
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no other secondary write '+route[-1])
        pages[here]=out
        if ip==0x39:
            prove(p,And(address(a)==0x6E,a.r[29]==0),'quiet return')
            break
    else:raise AssertionError('unclosed secondary path')
    assert writes==[('X','V'),('Y','X')]
    print('PASS secondary:',' -> '.join(route),flush=True)
    print('RESULT: V -> X and old X -> Y; all Ms held; Y marker is removed.',flush=True)


def clear_t(start):
    """RCL0 converges on A7(V), skipping T, without touching X1."""
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    address=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    tag='yt_clear_t_'+start
    pages={n:State(tag+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==0,a.r[33]==6,pages['U'][21]!=15,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','T') else pages[n][22]!=15)
    route=[];reads=[];written=[];carried=None
    for step in range(100):
        p.push();ips=q['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];nxt=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here]
        if ip==0xEE:
            reads.append(here)
            if len(reads)==2:
                assert here=='X' and written==['X','Y','Z','T']
                prove(p,And(a.st[36]==3,a.st[39]==14),'late reader returns E3')
                for n in slots:
                    if n in written:continue
                    prove(p,And(*[pages[n][j]==original[n][j] for j in range(42)]),'untouched '+n)
                prove(p,And(*[pages[n][22]!=15 for n in slots if n!='marker']), 'only real marker remains')
                print('PASS RCL0 clear T:', ' -> '.join(route),flush=True)
                return
        out=[];a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip==0xD6:
            assert here=='U';carried=[old[3*j] for j in range(12)]
        if ip in (0xE7,0xA8):
            assert carried is not None
            prove(p,And(*[out[1+3*j]==carried[j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact push '+here)
            carried=[old[1+3*j] for j in range(12)];written.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no extra write '+route[-1])
        pages[here]=out
    raise AssertionError('no bounded late reader')


def formatters():
    check=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    check(0,0,True,source_slot='X',marker_slots=('marker','T'),target_by_class=['W']*6+['X']*3)
    check(9,1,False,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)
    check(9,0,False,source_slot='X',marker_slots=('marker',),target_by_class=['X']*9)


if __name__=='__main__':
    primary();secondary()
    clear_t('control');clear_t('U');formatters()
    print('LIMIT: accepted primary 9C(control), secondary 6E(Y) with R29=0; '
          'RCL0 and three separate canonical formatter contracts; '
          'no native scheduling, universal numerical domain, or full K1 theorem.',flush=True)
