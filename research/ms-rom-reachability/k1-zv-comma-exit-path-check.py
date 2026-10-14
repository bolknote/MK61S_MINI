#!/usr/bin/env python3
"""Local ROM paths for the disposable operand, not a universal numeric exit."""
import runpy
import sys
from pathlib import Path
from z3 import And, BitVec, If, UGE, ULE, ZeroExt, sat, unsat

root=Path(__file__).resolve().parent
slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']

def prove(p,claim,label):
    assert p.check()==sat,('empty premise',label)
    p.push();p.add(~claim);answer=p.check();p.pop();assert answer==unsat,label

def sign(header='002'):
    assert header in ('002','003','983'), 'only the selected fixed exponent contracts'
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    S,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
    addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
    pages={n:S('chs_'+n).m for n in slots};a=S('chs');a.m=pages['control'];p=base(a,0x9C)
    p.add(a.r[30]==11,a.r[33]==0,a.s1==11,a.r[41]==15,a.st[35]==15,a.st[25]==0,
          If(a.m[31]==15,UGE(a.m[34],1),UGE(a.m[34],7)))
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z') else pages[n][22]!=15)
    digits=[BitVec('chs_digit'+str(j),4) for j in range(3)]
    p.add(*[ULE(d,9) for d in digits],UGE(digits[0],1),UGE(digits[2],1))
    source=[0]*5+list(reversed(digits))+[0,*map(int,reversed(header))]
    p.add(*[pages['V'][1+3*j]==v for j,v in enumerate(source)])
    route=[];reads=[]
    for step in range(100):
        p.push();ips=q['possible_values'](addr(a),p,257);p.pop();assert len(ips)==1,(route,ips)
        ip=ips[0];here=slots[(1+step)%15];following=slots[(2+step)%15];old=pages[here]
        route.append('%02X(%s)'%(ip,here))
        assert ip not in (0xE9,0xA3,0xA8,0xD4,0xD6)
        if ip==0xEE:reads.append(here)
        out=[];a=ex(a,ip,*keys('chs_'+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip==0xE7:
            assert here=='X' and reads==['V']
            negative=source[:];negative[8]=9
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(negative)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'only negated V to X')
            print('PASS CHS fresh-reads positive three-significant-digit V, header '+header+
                  ', and writes its negative to X; no push.',flush=True)
            print('PATH',' -> '.join(route),flush=True);return
        prove(p,And(*[x==y for x,y in zip(out,old)]),'no other CHS write '+route[-1]);pages[here]=out
    raise AssertionError('no bounded CHS output')

def reciprocal():
    """Optional stronger experiment; currently times out at address step 42.

    This is NOT part of the passing default contract. The native full-write
    audit verifies the two composed fixtures independently of this attempt.
    """
    q=runpy.run_path(str(root/'analyze_ms_pending_opcodes.py'))
    S,ex,base,keys,addr=(q[n] for n in ('State','ex','base','keys','address'))
    pages={n:S('recip_'+n).m for n in slots};a=S('recip');a.m=pages['marker']
    # Substitute the same fixed local premises into the symbolic model so
    # constant folding does not carry a symbolic long-division expression.
    # This changes no native emulator state and leaves all other words free.
    n4=q['q']['N4'];a.r[29]=n4(0);a.r[36]=n4(0x6E);a.r[39]=n4(6)
    for j,v in ((28,2),(31,3),(34,2)):pages['control'][j]=n4(v)
    for j,v in ((36,10),(39,3),(37,10),(40,3)):a.st[j]=n4(v)
    for j,v in enumerate(reversed('002910900000')):pages['X'][1+3*j]=n4(int(v,16))
    p=base(a,0x6E);p.set(timeout=10000)
    for n in slots:p.add(pages[n][22]==15 if n in ('marker','Z') else pages[n][22]!=15)
    route=[];writes=[]
    for step in range(160):
        p.push()
        try:ips=q['q']['possible_values'](addr(a),p,257)
        except AssertionError as error:raise AssertionError(('reciprocal address',step,route,str(error))) from error
        finally:p.pop()
        assert len(ips)==1,(route,ips)
        ip=ips[0];here=slots[step%15];following=slots[(step+1)%15];old=pages[here]
        route.append('%02X(%s)'%(ip,here));out=[]
        a=ex(a,ip,*keys('recip_'+str(step)),serial_inputs=pages[following],emitted_outputs=out)
        if ip==0x27:
            assert here=='control'
            prove(p,And(out[31]==15,*[out[j]==old[j] for j in range(42) if j!=31]),'only ACK')
            writes.append('ACK')
        elif ip==0x2A:
            assert here=='X'
            result=[int(v,16) for v in reversed('997991743119')]
            prove(p,And(*[out[1+3*j]==v for j,v in enumerate(result)],
                        *[out[j]==old[j] for j in range(42) if j%3!=1 or j>=37]),'only reciprocal X')
            writes.append('X')
        else:prove(p,And(*[x==y for x,y in zip(out,old)]),'no other reciprocal write '+route[-1])
        pages[here]=out
        if ip==0x39:
            assert writes==['ACK','X']
            prove(p,And(addr(a)==0x6E,a.r[29]==0),'quiet return')
            print('PASS local reciprocal -109: exact X=997991743119; only one ACK and twelve output tetras.',flush=True)
            print('PATH',' -> '.join(route),flush=True);return
    raise AssertionError('no bounded reciprocal return')

if __name__=='__main__':
    sign()
    if '--reciprocal-experiment' in sys.argv:reciprocal()
    request=runpy.run_path(str(root/'k1-ytv-request-path-check.py'))['request']
    for code in (0x23,0x36):
        result=request('T',code,('Z',))
        assert result['reads']==['X'] and result['writes']==[('E9','U'),('A3','control')]
    fmt=runpy.run_path(str(root/'k1-q-formatter-check.py'))['check']
    fmt(9,0,source_slot='X',marker_slots=('marker','Z'),target_by_class=['V']*9)
    print('LIMIT: secondary reciprocal arithmetic is covered by native audits, not a completed SMT theorem. '
          'Scheduler and max order need separate checks; R8=109 is still a fixture constraint.',flush=True)
