#!/usr/bin/env python3
"""Local accepted-request maps for real/Y/T markers; no keyboard search."""
import runpy
from pathlib import Path
from z3 import And, If, UGE, ZeroExt, BitVecVal, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots = ['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr = lambda a: ZeroExt(4,a.r[36]) | (ZeroExt(4,a.r[39]) << 4)


def prove(p, claim, label):
    assert p.check() == sat, ('empty premise', label)
    p.push(); p.add(~claim); result = p.check()
    assert result == unsat, (label, p.model() if result == sat else result)
    p.pop()


def check(start, code, verbose=False):
    tag = 'yt_read_%s_%02x' % (start, code)
    pages = {n:State(tag+'_'+n).m for n in slots}
    a=State(tag); a.m=pages[start]; p=base(a,0x9C)
    p.add(a.r[30] == (code & 15), a.r[33] == (code >> 4),
          If(pages[start][31] == 15, UGE(pages[start][34],1), UGE(pages[start][34],7)))
    if code in (0x0E,0x0F): p.add(a.s1==code)
    for n in slots:
        p.add(pages[n][22] == 15 if n in ('marker','Y','T') else pages[n][22] != 15)
    route = []; reads = []
    for step in range(100):
        p.push(); ips=q['possible_values'](addr(a),p,257); p.pop()
        assert len(ips)==1, ('not forced',route,ips)
        ip=ips[0]; here=slots[(slots.index(start)+step)%15]
        following=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here)); out=[]
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip == 0xD4:
            assert reads and reads[0][0] == 'EE'
            source = reads[0][1]
            prove(p,And(*[out[3*j] == pages[source][1+3*j] for j in range(12)],
                        *[out[j] == pages[here][j] for j in range(42) if j%3!=0 or j>=36]),
                  'STORE only exact M1 numeric source')
        else:
            prove(p,And(*[x==y for x,y in zip(out,pages[here])]),'no prior ring write '+route[-1])
        if ip in (0xEE,0xD6):
            lane=1 if ip==0xEE else 0
            prove(p,And(*[a.r[3*j]==pages[here][lane+3*j] for j in range(12)]),
                  'exact complete source read')
            reads.append(('%02X'%ip,here))
        if ip in (0xD4,0xD6) or (ip == 0xEE and code in (0x0E,0x0F)):
            p.push(); nextips=q['possible_values'](addr(a),p,257); p.pop()
            result={'accepted9C':start,'opcode':'%02X'%code,'read':'%02X'%ip,
                    'source':here,'reads':reads,'return':['%02X'%n for n in nextips], 'commands':len(route)}
            expected_first = ('U' if start=='control' else 'X') if code==0x0E else (
                ('T' if start=='control' else 'X1') if code==0x0F else
                ('W' if start=='control' else 'X'))
            assert reads[0] == ('EE',expected_first), result
            if code in (0x40,0x60): assert here == 'U',result
            print('PASS', result, flush=True)
            if verbose: print('PATH',' -> '.join(route), flush=True)
            return result
    raise AssertionError('no bounded read')


def continuation(start, code=0x0F):
    tag='yt_second_%02x_' % code+start
    pages={n:State(tag+'_'+n).m for n in slots}; original=dict(pages)
    a=State(tag); a.m=pages[start]; p=base(a,0x9C)
    p.add(a.r[30]==(code & 15),a.r[33]==(code >> 4),
          If(pages[start][31]==15,UGE(pages[start][34],1),UGE(pages[start][34],7)))
    if code in (0x0E,0x0F): p.add(a.s1 == code)
    for n in slots:
        p.add(pages[n][22]==15 if n in ('marker','Y','T') else pages[n][22]!=15)
    route=[]; reads=[]; writes=[]; carried=None
    for step in range(150):
        p.push(); ips=q['possible_values'](addr(a),p,257); p.pop()
        assert len(ips)==1,('unforced second read',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15]
        following=slots[(slots.index(start)+step+1)%15]; old=pages[here]
        route.append('%02X(%s)'%(ip,here))
        if ip==0xEE:
            reads.append(here)
            if len(reads)==1: carried=[old[1+3*j] for j in range(12)]
            if len(reads)==2:
                expected_writes = ['W','Q','P7','P8'] if code==0x0F and start!='control' else ['X','Y','Z','T']
                assert writes==expected_writes,writes
                expected_first = ('T' if start=='control' else 'X1') if code==0x0F else (
                    'W' if start=='control' else 'X')
                assert reads==[expected_first,'X'],reads
                prove(p,And(a.st[36]==3,a.st[39]==14),'second EE returns E3')
                for n in slots[7:]:
                    if n in writes: continue
                    prove(p,And(*[pages[n][j]==original[n][j] for j in range(42)]),
                          'unwritten stored Ms page held '+n)
                print('PASS connected %02X' % code,start,'reads',reads,'writes',writes,flush=True)
                print('PATH',' -> '.join(route),flush=True)
                return {'start':start,'reads':reads}
        out=[];a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip == 0xD6:
            carried=[old[3*j] for j in range(12)]
        if ip in (0xE7,0xA8):
            assert carried is not None
            prove(p,And(*[out[1+3*j]==carried[j] for j in range(12)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),
                  'exact visible transfer '+route[-1])
            carried=[old[1+3*j] for j in range(12)];writes.append(here)
        else:
            prove(p,And(*[x==y for x,y in zip(out,old)]),'no extra write '+route[-1])
        pages[here]=out
    raise AssertionError('no bounded second EE')


def scanner_and_late_formatter():
    a=State('yt_scan'); p=base(a,0x9B)
    b=ex(a,0x9B,*keys('yt_scan_keys'))
    prove(p,addr(b)==If(a.m[22]==15,BitVecVal(0x9C,8),BitVecVal(0x9B,8)),
          '9B selects 9C iff matched marker')
    assert [slots[(slots.index(n)+1)%15] for n in ('marker','Y','T')] == ['control','Z','U']
    print('PASS real/Y/T marker scanner: only control/Z/U may host 9C.',flush=True)
    formatter=runpy.run_path(str(Path(__file__).with_name('k1-q-formatter-check.py')))['check']
    # After the proven visible push, real and Z are the remaining markers.
    # ENTER's v has class 0; RCL0's w has class 1 for the current defaults.
    geometry={'source_slot':'X','marker_slots':('marker','Z'),
              'target_by_class':['V']*5+['X']*4}
    formatter(9,0,False,**geometry)
    formatter(9,1,False,**geometry)
    print('PASS separate canonical late-return contracts: ENTER default v '
          'and RCL0 default w are copied X -> V, overwriting unique u.',flush=True)


if __name__=='__main__':
    for code in (0x0E,0x0F,0x60,0x40):
        for start in ('control','Z','U'):
            check(start,code,True)
    for start in ('control','Z','U'):
        continuation(start)
        continuation(start,0x60)
    scanner_and_late_formatter()
    print('LIMIT: primary accepted-9C prefixes and LastX/RCL0 continuations '
          'through second EE plus two separate canonical formatters only; '
          'not keyboard phase, a universal formatter result, or a '
          'whole-machine preservation theorem.', flush=True)
