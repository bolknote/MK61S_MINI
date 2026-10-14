#!/usr/bin/env python3
"""Accepted-control read geometry before upperwrite; no native phase search."""
import runpy
from pathlib import Path
from z3 import If, UGE, ULT, BitVecVal, BV2Int, ZeroExt, sat, unsat, And

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, ex, base, keys = (q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
slots = ['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
addr = lambda a: ZeroExt(4,a.r[36]) | (ZeroExt(4,a.r[39]) << 4)

def check(start, code):
    tag='nop_reserve_%s_%02x'%(start,code)
    pages={n:State(tag+'_'+n).m for n in slots}
    a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==(code&15),a.r[33]==(code>>4),
          If(pages[start][31]==15,UGE(pages[start][34],1),UGE(pages[start][34],7)))
    if code in (0x0E,0x0F):
        p.add(a.s1==code)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','T','V') else pages[n][22]!=15)
    route=[]
    for step in range(100):
        p.push();ip=q['possible_values'](addr(a),p,257);p.pop()
        assert len(ip)==1,('not forced',route,ip)
        ip=ip[0];here=slots[(slots.index(start)+step)%15]
        following=slots[(slots.index(start)+step+1)%15]
        route.append('%02X(%s)'%(ip,here));out=[]
        a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        p.push();p.add(~And(*[x==y for x,y in zip(out,pages[here])]))
        answer=p.check();p.pop();assert answer==unsat,('unexpected prior write',route)
        if ip==0xEE:
            p.push();p.add(~And(*[a.r[3*j]==pages[here][1+3*j] for j in range(12)]))
            answer=p.check();p.pop();assert answer==unsat,('inexact read',route)
            p.push();nextip=q['possible_values'](addr(a),p,257);p.pop()
            result={'accepted9C':start,'opcode':'%02X'%code,'source':here,'return':nextip,
                    'commands':len(route)}
            print('PASS',result,flush=True)
            if here=='Q': print('PATH',' -> '.join(route),flush=True)
            return result
    raise AssertionError('no EE')

def lastx_q(start='Z',source='Q'):
    """Connect accepted Z/Q or control/V to both EE reads, including push."""
    tag='nop_reserve_connected_'+source
    pages={n:State(tag+'_'+n).m for n in slots}
    original=dict(pages);a=State(tag);a.m=pages[start];p=base(a,0x9C)
    p.add(a.r[30]==15,a.r[33]==0,a.s1==15,
          If(pages[start][31]==15,UGE(pages[start][34],1),UGE(pages[start][34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','T','V') else pages[n][22]!=15)
    route=[];reads=[];writes=[];carried=None
    def prove(claim,label):
        assert p.check()==sat,('empty',label)
        p.push();p.add(~claim);result=p.check();p.pop();assert result==unsat,label
    for step in range(150):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop()
        assert len(ips)==1,('unforced',route,ips)
        ip=ips[0];here=slots[(slots.index(start)+step)%15]
        following=slots[(slots.index(start)+step+1)%15];old=pages[here]
        route.append('%02X(%s)'%(ip,here))
        if ip==0xEE:
            reads.append(here)
            if len(reads)==1:
                assert here==source,(source,route)
                carried=[old[1+3*j] for j in range(12)]
            if len(reads)==2:
                assert here=='P7',route
                prove(And(a.st[36]==3,a.st[39]==14),'second EE returns to E3')
                assert writes==['X','Y','Z','T'],writes
                for dest,origin in zip(['X','Y','Z','T'],[source,'X','Y','Z']):
                    prove(And(*[pages[dest][1+3*j]==original[origin][1+3*j] for j in range(12)]),
                          'result '+dest+' <- '+origin)
                print('PASS connected LastX '+source+': only visible push, second EE(P7)->E3, no E9/A3.',flush=True)
                print('PATH',' -> '.join(route),flush=True)
                return
        out=[];a=ex(a,ip,*keys(tag+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip in (0xE7,0xA8):
            prove(And(*[out[1+3*j]==carried[j] for j in range(12)],
                      *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'exact '+route[-1])
            carried=[old[1+3*j] for j in range(12)];writes.append(here)
        else:prove(And(*[x==y for x,y in zip(out,old)]),'no extra write '+route[-1])
        pages[here]=out
    raise AssertionError('no second EE')

def scanner():
    """The actual marker scanner cannot select arbitrary accepted origins."""
    for ip in (0x9B,0x9C,0x9D,0x96,0x97,0x99):
        a=State('nop_scan_%02x'%ip);p=base(a,ip);out=[]
        b=ex(a,ip,*keys('scan_%02x'%ip),emitted_outputs=out)
        if ip==0x9B:expected=If(a.m[22]==15,0x9C,0x9B)
        elif ip==0x9C:expected=If(If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)),0x9E,0x9D)
        elif ip==0x9D:
            count=ZeroExt(1,a.r[32])+If(a.r[29]==15,BitVecVal(1,5),BitVecVal(0,5))
            expected=If(UGE(count,10),0x96,0x97)
        elif ip==0x96:expected=0xA2
        elif ip==0x97:expected=If(ULT(a.r[2],8),0x99,0x63)
        else:expected=If(a.r[26]==0,0x9B,0x74)
        assert p.check()==sat
        p.push();p.add(BV2Int(addr(b))!=expected);assert p.check()==unsat,('scanner route',ip);p.pop()
        p.push();p.add(~And(*[x==y for x,y in zip(out,a.m)]));assert p.check()==unsat,('scanner writes',ip);p.pop()
        print('PASS scanner %02X exact next address and ring held'%ip,flush=True)
    next_pages=[slots[(slots.index(n)+1)%15] for n in ('marker','T','V')]
    assert next_pages==['control','U','W']
    print('PASS real/T/V 9B scanner can reach 9C only at control/U/W; never Y/Z.',flush=True)

if __name__=='__main__':
    import sys
    if '--scanner-only' in sys.argv:
        scanner();sys.exit()
    if '--connected-only' in sys.argv:
        lastx_q();lastx_q('control','V');sys.exit()
    for code in (0x0E,0x0F,0x40):
        for start in slots:check(start,code)
    lastx_q()
    lastx_q('control','V')
    scanner()
    print('LIMIT: 45 early-read maps, two LastX suffixes through second EE, '
          'and local marker-scanner gate. No native keyboard realization, '
          'other-chip interaction, late formatter or full K1 is proved here.',flush=True)
