#!/usr/bin/env python3
"""D4's completed no-EE context inventory and exact return protocols.

All positive entries are detached source hypotheses, NOT keyboard witnesses.
No ROM/reference state is edited. The AF escape requires R34=4 and the
nonstandard incoming B8 in D..F; neither is supplied by the current native
cache bridge. All six payload tetras and future ring/key signals are free.
Quiet33 is a local released-key exit, not a fixed physical press schedule.
Only primary writes are proved here; whole-ring persistence is separate.
"""
from collections import Counter,deque
from pathlib import Path
import runpy

from z3 import And,If,Or,UGE,ULE

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache46-writer-contracts.py'))
q=w['q']
State,ex,base,keys=(q[n] for n in
                  ('State','execute_command','base_solver','arbitrary_keys'))
ip,eq,A,prove,stack=(w[n] for n in ('ip','eq','A','prove','stack'))
packet=(0xDC,0xDE,0xD4,0xDD,0xD4)
af_cycle=packet+(0xAF,0xAE)
restore=(0xD1,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,
         0x93,0x94,0x95,0x98,0x9A)


def context_inventory():
    g=runpy.run_path(str(root/'cache-numeric-export-gates.py'))
    states,edges=g['states'],g['edges']
    reached={j for j,s in enumerate(states) if s[0]==0xC9}
    assert len(reached)==146
    todo=deque(sorted(reached))
    while todo:
        j=todo.popleft()
        if states[j][0]==0xEE:continue
        for k in edges[j]:
            if k not in reached:reached.add(k);todo.append(k)
    assert len(reached)==10695
    contexts=[j for j in reached if states[j][0]==0xD4]
    assert len(contexts)==63
    counts=Counter(states[j][1][0] for j in contexts)
    assert counts=={0xDD:27,0xAF:6,0xC3:9,0x76:12,0xCF:9}
    assert all(states[j][2]==0xD8 and states[j][3]==[4]
               and states[j][7]==[0] for j in contexts)
    parents=Counter()
    for j in reached:
        if states[j][0]==0xEE:continue
        for k in edges[j]:
            if k in contexts:parents[states[j][0]]+=1
    assert set(parents)=={0xDE,0xDD}
    print('PASS completed C9/noEE cut:63 D4 contexts; '
          'all vectorD8/S1=4/R26=0; only DE/DD inlets.',flush=True)
    print('PASS return-family counts:',
          {f'{n:02X}':counts[n] for n in sorted(counts)},flush=True)
    assert all(states[j][1][0] not in (0x33,0x35,0x7F) for j in contexts)
    print('LIMIT: graph contexts are not native entries or payload witnesses; '
          'there is no immediate idle/quiet return among them.',flush=True)


def step(p,a,code,label,quiet=False):
    prove(p,ip(a)==code,label+' source',False)
    out=[]
    b=ex(a,code,*( (0,0) if quiet else keys(label+'_keys') ),emitted_outputs=out)
    if code!=0xD4:prove(p,eq(out,a.m),label+' no outgoing write',False)
    return b,out


def af_gate():
    a=State('d4_af_gate');p=base(a,0xAF)
    p.add(a.r[34]==4,a.r[26]==0)
    b,out=step(p,a,0xAF,'d4_af_gate')
    prove(p,And(ip(b)==0xAE,eq(A(b),A(a)),
                eq(b.r[1:34:3],a.r[1:34:3]),
                b.r[34]==If(UGE(a.r[21],13),q['N4'](1),q['N4'](4))),
          'AF exact gate at R26=0/header4: new header1 iff A7 is D/E/F; '
          'otherwise header4; A12 and B0..10 held')


def af_protocol(escaping):
    label='d4_af_escape' if escaping else 'd4_af_loop'
    a=State(label);p=base(a,0xDC)
    p.add(a.r[34]==4,a.r[26]==0,stack(a)[0]==0xAF,
          UGE(a.r[25],13) if escaping else ULE(a.r[25],12))
    b=a;writes=[]
    for j,code in enumerate(af_cycle):
        if code==0xAF:
            prove(p,b.r[21]==a.r[25],
                  'DD exposes original B8 as A7, independently of every raw code',False)
        before=b;b,out=step(p,b,code,f'{label}_{j}')
        if code==0xD4:
            writes.append(out)
            prove(p,And(*[out[k]==before.m[k] for k in range(42)
                          if k not in range(0,36,3)]),
                  'D4 preserves all M2/M3 and all other outgoing tetras',False)
    prove(p,And(ip(b)==0xDC,b.r[26]==0,stack(b)[0]==0xAF,
                eq(b.r[1:34:3],a.r[1:34:3]),
                b.r[34]==(1 if escaping else 4)),
          'AF escape selects header1 at the next DC' if escaping else
          'AF LOOP INDUCTION: DC DE D4 DD D4 AF AE returns to the '
          'same control class forever for ANY B8=0..C, including native0')
    prove(p,And(*[writes[0][k+3]==a.r[k] for k in w['raw']],
                *[writes[1][k]==a.r[k] for k in w['raw']]),
          'both primary M1 writes contain ALL six raw code tetras, exactly reversible')
    if not escaping:return
    sequence=(0xDC,0xDE)+restore+(0xD2,)+(0x30,)*5+(0x31,0x33)
    for j,code in enumerate(sequence):
        b,_=step(p,b,code,f'd4_escape_tail_{j}',quiet=code==0x33)
    prove(p,ip(b)==0x35,
          'CONDITIONAL D/E/F B8 escape: after the two D4 writes, '
          'D1 restoration/D2/five30/31/quiet33 reach35 with NO further primary write')
    print('CONDITIONAL finite route:',
          ' '.join(f'{c:02X}' for c in af_cycle+sequence),'→35',flush=True)
    print('LIMIT: two constructed metadata fields (header4/B8 D..F), '
          'not native entry, not Ms destination, not full-ring persistence '
          'or an executable keyboard protocol.',flush=True)


def c3_loop_and_cf_inlet():
    # C2 itself creates C3; no assumption about the old return stack is needed.
    a=State('d4_c2_packet');p=base(a,0xC2);p.add(a.r[34]==4)
    b=a
    for j,code in enumerate((0xC2,)+packet):
        b,_=step(p,b,code,f'd4_c2_packet_{j}')
    prove(p,And(ip(b)==0xC3,b.r[34]==4),
          'ANY C2/header4 entry returns through its own C3 after the two D4 writes')
    a=State('d4_c3_loop');p=base(a,0xC3);p.add(a.r[34]==4)
    b=a
    for j,code in enumerate((0xC3,0xC2)+packet):
        b,_=step(p,b,code,f'd4_c3_loop_{j}')
    prove(p,And(ip(b)==0xC3,b.r[34]==4),
          'C3 LOOP INDUCTION: C3 C2 DC DE D4 DD D4 repeats forever '
          'for any other state, serial inputs and per-tick keys')
    a=State('d4_cf_inlet');p=base(a,0xCF)
    p.add(a.r[34]==4,a.s1==4)
    b,_=step(p,a,0xCF,'d4_cf_inlet')
    prove(p,And(Or(ip(b)==0xC2,ip(b)==0xC3),b.r[34]==4),
          'CF/S1=4/header4 necessarily enters C2 or C3, then the proved endless C3 loop')


def other_returns():
    a=State('d4_return_word');p=base(a,0xD4);p.add(a.s1==4)
    out=[];b=ex(a,0xD4,*keys('d4_return_word_keys'),emitted_outputs=out)
    prove(p,And(ip(b)==stack(a)[0],eq(stack(b),stack(a)[1:]+stack(a)[:1]),
                eq(A(b),A(a)),b.s1==4,
                eq(out[0:36:3],[a.s]+A(a)[:11])),
          'D4 writes S+A0..10, holds A12/S1=4, rotates old return stack')
    a=State('d4_dd_word');p=base(a,0xDD);p.add(a.s1==4)
    b,_=step(p,a,0xDD,'d4_dd_word')
    prove(p,And(ip(b)==0xD4,b.s1==4,eq(stack(b),stack(a)),
                eq(A(b),A(a)[1:]+A(a)[:1])),
          'DD rotates all12 A losslessly and returns to D4; '
          'all-DD stack loops forever, otherwise exits at the first non-DD tag')
    a=State('d4_return76');p=base(a,0x76)
    b=a
    for j,code in enumerate((0x76,0xE2,0xE5,0xE6,0xED)):
        if code==0xE5:p.add(b.m[22]==15)
        b,_=step(p,b,code,f'd4_return76_{j}')
    prove(p,ip(b)==0xEE,
          '76 forces nested E2 E5* E6 ED EE; no primary write before EE')
    print('LIMIT: after an EARLIER D4 export, an EE read is NOT itself '
          'a proof that the physically stored copy is lost. Family76 '
          'still needs destination/retention/exit analysis.',flush=True)


if __name__=='__main__':
    context_inventory()
    af_gate()
    af_protocol(False)
    af_protocol(True)
    c3_loop_and_cf_inlet()
    other_returns()
    print('PASS exact D4 context/return contracts. Partial K2 remains unbuilt; '
          'no keyboard witness is asserted.',flush=True)
