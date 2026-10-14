#!/usr/bin/env python3
"""Exact secondary 14h paths: when does a swap remove a hidden marker?

These are local ROM contracts, not keyboard reachability or whole K1.
"""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
State,ex,base,keys,address=(q[n] for n in ('State','ex','base','keys','address'))
slots=q['slots']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop()
    assert answer==unsat,label

def swap(start,extra,expected,expected_acks,remaining):
    tag='deep_swap_'+start+'_'+''.join(extra)
    pages={n:State(tag+'_'+n).m for n in slots};original=dict(pages)
    a=State(tag);a.m=pages[start];p=base(a,0x6E)
    request=slots[(slots.index(start)+1)%15]
    p.add(a.r[29]==0,pages[request][34]==1,pages[request][31]==4)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker',*extra) else pages[n][22]!=15)
    route=[];writes=[];acks=[]
    for step in range(80):
        p.push();ips=q['q']['possible_values'](address(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15];nxt=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));old=pages[here];out=[]
        a=ex(a,ip,*keys(tag+'_'+str(step)),serial_inputs=pages[nxt],emitted_outputs=out)
        if ip in (0x4E,0x2A):
            target,source=expected[len(writes)]
            assert here==target,('target',route,expected)
            prove(p,And(*[out[1+3*j]==original[source][1+3*j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact '+source+' -> '+target)
            writes.append((target,source))
        elif ip==0x27:
            assert here==expected_acks[len(acks)],('ACK',route,expected_acks)
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only ACK')
            acks.append(here)
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no undeclared output '+route[-1])
        pages[here]=out
        if ip==0x39:
            prove(p,And(address(a)==0x6E,a.r[29]==0),'quiet return');break
    else:raise AssertionError('no bounded return')
    assert writes==expected and acks==expected_acks
    for n in slots:
        prove(p,pages[n][22]==15 if n in ('marker',*remaining) else pages[n][22]!=15,'exact markers after return: '+n)
    print('PASS',{'start':start,'markers':extra,'copies':writes,'acks':acks,'remaining':remaining},flush=True)
    print('PATH',' -> '.join(route),flush=True)

def nop_source(start,extra=('Y','T','U','V')):
    primary=runpy.run_path(str(root/'ik1302_symbolic.py'))
    S,execute,solver,key=(primary[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    tag='deep_nop_'+start;pages={n:S(tag+n).m for n in slots}
    a=S(tag);a.m=pages[start];p=solver(a,0x9C)
    p.add(a.r[30]==4,a.r[33]==5,a.r[23]==0,a.r[26]==0,a.r[29]==4)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker',*extra) else pages[n][22]!=15)
    for marker in ('marker',*extra):
        n=slots[(slots.index(marker)+1)%15]
        p.add(If(pages[n][31]==15,UGE(pages[n][34],1),UGE(pages[n][34],7)))
    path=[];reads=[];gates=[]
    for step in range(120):
        p.push();ips=primary['possible_values'](addr(a),p,257);p.pop()
        assert len(ips)==1,('unforced NOP',path,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15]
        following=slots[(slots.index(start)+step+1)%15]
        path.append('%02X(%s)'%(ip,here));old=pages[here]
        if ip==0x9C:gates.append(here)
        if ip==0xEE:
            reads.append(here)
            if len(reads)==2:
                assert gates==([start,'Z'] if start=='control' else [start,'control']),gates
                assert reads==(['W','X'] if start=='control' else ['X','Q']),reads
                prove(p,And(a.st[36]==3,a.st[39]==14),'late return E3')
                print('PASS NOP geometry',{'start':start,'gates':gates,'reads':reads,'writesBeforeLate':[]},flush=True)
                print('PATH',' -> '.join(path),flush=True)
                return reads[-1]
        out=[];a=execute(a,ip,*key(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        prove(p,And(*[x==y for x,y in zip(old,out)]),'NOP has no early write '+path[-1])
        pages[here]=out
    raise AssertionError('NOP did not reach a bounded late reader')

def marker_formatter():
    """The late reader sees m before the concurrent secondary X/Y output.

    Normalization uses arbitrary subsequent ring inputs. The final marker
    scan assumes the post-swap real/Y/T/V geometry, not an injected u.
    """
    primary=runpy.run_path(str(root/'ik1302_symbolic.py'))
    S,execute,solver,key=(primary[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    a=S('old_x_marker');p=solver(a,0xEE);p.add(a.st[36]==3,a.st[39]==14)
    source=[int(x,16) for x in reversed('9990FFFFFFF0')]
    p.add(*[a.m[1+3*j]==v for j,v in enumerate(source)])
    sequence=[int(x,16) for x in ('EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D9 '
        'F3 F7 F1 F3 F7 F1 F4 F6 F4 F6 F4 F6 F4 F6 F4 F6 F4 F6 F4 F6 F4 EA EC '
        '40 41 42 46 E5 E5 E5 E6 E8 E7').split()]
    for i,ip in enumerate(sequence):
        here=slots[(slots.index('X')+i)%15];label='late marker %02X(%s)'%(ip,here)
        if ip==0xE5:p.add(a.m[22]==15 if here in ('marker','Y','T','V') else a.m[22]!=15)
        prove(p,addr(a)==ip,label+' forced address')
        old=a.m;out=[];a=execute(a,ip,*key(label),emitted_outputs=out)
        if ip==0xE7:
            assert here=='U'
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(source)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),label+' exact m only')
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),label+' no write')
    prove(p,addr(a)==0x47,'marker formatter returns to 47')
    print('PASS fixed noncanonical marker: late EE(X=m) -> exact E7(U=m); no other write.',flush=True)

if __name__=='__main__':
    swap('Y',('Y',),[('X','V'),('Y','X')],['control'],())
    swap('V',('V',),[('P7','P8'),('P8','P7')],['W'],('V',))
    swap('V',('Y','V'),[('U','P8'),('V','U')],['Z'],('Y',))
    for start in ('control','Z','U','V','W'):nop_source(start)
    marker_formatter()
    runpy.run_path(str(root/'k1-q-formatter-check.py'))['check'](9,0,source_slot='X',
        marker_slots=('marker','Y','T','U','V'),target_by_class=['U']*9)
    print('PASS NOP negative-exponent class-0 u: late EE(X=u) -> exact E7(U=u).',flush=True)
    print('LIMIT: the second path does not remove V; the third needs a separately reachable Y marker and safe primary writes.',flush=True)
