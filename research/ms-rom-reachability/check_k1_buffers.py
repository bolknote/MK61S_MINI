#!/usr/bin/env python3
"""Exact local K1 buffer contracts, plus cut-point checks of candidate paths."""
import runpy
from pathlib import Path
from z3 import And, Or, ZeroExt, sat, unsat


def byte(lo,hi):return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)


def local_checks(q):
    def check(ip, label, claim, condition=lambda a:True):
        a=q['State'](f'k1_local_{ip}_{label[:4]}')
        b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'k1_local_keys_{ip}'))
        p=q['base_solver'](a,ip);p.add(condition(a))
        assert p.check()==sat,label
        p.add(~claim(a,b));assert p.check()==unsat,label
        print('PASS:',label,flush=True)
    check(0x91,'91 exchanges both twelve-tetrade working words',lambda a,b:
          And(*[b.r[3*i]==a.r[1+3*i] for i in range(12)],
              *[b.r[1+3*i]==a.r[3*i] for i in range(12)]))
    check(0xA9,'A9 replaces two upper A tetras from R32/R35',lambda a,b:
          And(*[b.r[3*i]==a.r[3*i] for i in range(10)],
              b.r[30]==a.r[32],b.r[33]==a.r[35]))
    check(0xDD,'DD rotates all twelve A tetras, preloads S, dispatches by S1',lambda a,b:
          And(*[b.r[3*i]==a.r[3*((i+1)%12)] for i in range(12)],
              b.s==a.r[0],byte(b.r[36],b.r[39])==(0xD0|ZeroExt(4,a.s1))))
    check(0xDE,'DE uses old R34, not old S1, to choose D4',lambda a,b:
          And(b.s1==a.r[34],byte(b.r[36],b.r[39])==(0xD0|ZeroExt(4,a.r[34]))))
    check(0xDE,'DE replaces A fields and is not DD alignment',lambda a,b:
          And(*[b.r[3*i]==a.r[3*i] for i in range(9)],
              b.r[27]==a.r[28],b.r[30]==a.r[31],b.r[33]==15))
    check(0xE7,'E7 with reachable selectors 0/7/8 cannot immediately select D4',lambda a,b:
          And(Or(b.s1==2,b.s1==9,b.s1==10),b.s1!=4),
          lambda a:Or(a.s1==0,a.s1==7,a.s1==8))


def exact_path(m, states, timeout_ms=10000):
    """Fresh states avoid recursively expanding an entire long ROM path.

    All inter-command R/ST/scalar data are constrained exactly. Serial input
    remains arbitrary, as in the controller analysis. UNSAT rejects this
    candidate; SAT still does not establish a keyboard or real-ring protocol.
    """
    q=m['q'];sequence=[]
    for state in states:
        ip=state[0];sequence.append(ip)
        if ip==0x93:sequence.append(0x94)
        if ip==0x12:sequence.append(0xC6)
    a=q['State']('k1_exact_initial');current=a
    p=q['base_solver'](a,sequence[0]);p.set(timeout=timeout_ms)
    ip,sp,vector,selector,delta,r38,dr38,r26,types=states[0]
    p.add(*[byte(a.st[36+i],a.st[39+i])==sp[i] for i in range(3)],
          Or(*[a.s1==v for v in selector]),Or(*[a.r[38]==v for v in r38]),
          Or(*[a.r[26]==v for v in r26]))
    if vector=='diagonal':p.add(a.r[37]==a.r[40])
    elif vector is not None:p.add(byte(a.r[37],a.r[40])==vector)
    if delta is not None:p.add(a.s1-a.r[35]==delta)
    if dr38 is not None:p.add(a.r[38]-a.r[35]==dr38)
    assert types is None
    result={'sequence':sequence,'initial':a,'solver':p}
    for index,ip in enumerate(sequence[:-1]):
        output=[]
        b=q['execute_command'](current,ip,*q['arbitrary_keys'](f'k1_exact_keys_{index}'),
                               emitted_outputs=output)
        following=q['State'](f'k1_exact_{index+1}')
        claims=[x==y for group in ('r','m','st')
                for x,y in zip(getattr(b,group),getattr(following,group))]
        claims += [getattr(b,n)==getattr(following,n) for n in ('s','s1','l','t','carry')]
        claims += [byte(following.r[36],following.r[39])==sequence[index+1]]
        p.assert_and_track(And(*claims),f'step_{index}_{ip:02X}_{sequence[index+1]:02X}')
        outcome=p.check()
        if outcome!=sat:
            print('Exact candidate:',outcome,'at',index,f'{ip:02X}->{sequence[index+1]:02X}',flush=True)
            if outcome==unsat:print('Core:',p.unsat_core(),flush=True)
            else:print('Reason:',p.reason_unknown(),flush=True)
            result.update(outcome=str(outcome),failed_step=index,current=following)
            return result
        current=following
        if index%20==19:print('Exact candidate prefix:',index+1,'transitions SAT',flush=True)
    # Check the actual final D4 outputs against the first E7 word.
    assert sequence[0]==0xE7 and sequence[-1]==0xD4
    output=[]
    q['execute_command'](current,0xD4,*q['arbitrary_keys']('k1_exact_final_keys'),
                         emitted_outputs=output)
    p.push();p.add(~And(*[output[3*i]==a.m[1+3*i] for i in range(12)]))
    transfer=p.check();p.pop()
    print('Exact path SAT; unequal full-word output:',transfer,
          '; E7-to-D4 phase difference:',(len(sequence)-1)%15,flush=True)
    result.update(outcome='sat',transfer=str(transfer),current=current)
    return result


if __name__=='__main__':
    q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
    local_checks(q)
