#!/usr/bin/env python3
"""ROM sign→CE→CA→DA source and return contracts, not a keyboard writer.

Native controls construct selector A and ST25=0/9 by keys alone. Positive
CE/DA states below are detached hypotheses: a nondecimal sign and a suitable
header have NOT been constructed on the reference. Arbitrary per-tick keys
and incoming ring data overapproximate real hardware for local UNSAT proofs.
The CF return is unconditionally trapped for the header4 writer packet.
"""
import json
from collections import Counter, deque
from pathlib import Path
import runpy
import subprocess

from z3 import And, Extract, If, Or, UGE, ULE, ZeroExt, sat

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache-writer-contract.py'));q=w['q']
State,ex,base,keys=(q[n] for n in ('State','execute_command','base_solver','arbitrary_keys'))
ip,stack,prove,constant,number=(w[n] for n in ('address','stack','prove','constant','number'))
raw=w['positions']
restore=(0x8C,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,
         0x93,0x94,0x95,0x98,0x9A,0x8D,0x4F)
eq=lambda xs,ys:And(*[x==y for x,y in zip(xs,ys)])


def native_replays(cases):
    for case in cases:
        for label,es in (('AC source',case['sourceEvents']),('sign prefix',case['prefix'])):
            b=constant(es[0])
            for event,following in zip(es,es[1:]):
                assert number(ip(b))==event['ip']
                b=ex(b,event['ip'],event['keyX'],event['keyY'],
                     serial_inputs=[q['N4'](v) for v in following['m']])
                for field in ('r','st','m'):
                    assert [number(v) for v in getattr(b,field)]==following[field]
                for field in ('s','s1','l','t','carry'):
                    assert number(getattr(b,field))==following[field]
            print('PASS exact native ALL primary fields:',label,
                  case['report']['fixture'],'selector',case['report']['selector'],
                  'carrier',case['report']['carrier'],len(es)-1,'macros.',flush=True)
        r=case['report']
        assert r['C8_ST25'] in (0,9) and r['atBF_next']==0xC0
        assert not r['nativeDA'] and r['raw3LostAtFirstEE']
    print('SCOPE: these native controls enter BF→C0, not CE/DA. '
          'Selector A alone is constructible; it is not a usable writer.',flush=True)


def recorded_sign_source(es):
    assert es[0]['ip']==0xAC and es[-1]['ip']==0xC8
    loads=[i for i,e in enumerate(es[:-1]) if e['ip']==0xD6]
    assert loads and loads[0]>0
    load=loads[0]
    assert es[load]['slot']=='Y'
    # A later D6 loads the malformed numeric pointer. ST25 instead comes
    # from the FIRST D6: M1 of physical pageY is ordinary register C.
    a=State('sign_source_AC');p=base(a,0xAC);b=a;source=None
    for j,event in enumerate(es[:-1]):
        if j==load:source=b.m[24]
        b=ex(b,event['ip'],*keys(f'sign_source_keys{j}'),
             serial_inputs=State(f'sign_source_serial{j}').m)
    assert source is not None
    prove(p,And(b.st[25]==source,b.st[24]==a.r[26],
                b.st[33]==a.r[35],b.st[35]==a.r[34]),
          'Recorded AC→C8 operators: ST25=ordinary-PC M1[24] beforeD6; '
          'ST24=AC.R26, ST33=AC.R35, ST35=AC.R34')
    print('SCOPE: universal dataflow of this recorded operator sequence, '
          'not every AC constructor. Native traces identify the D6 source '
          'as ordinary register C; its sign is0/9 in these controls.',flush=True)


def sign_gate_and_packet():
    a=State('sign_da_8C');p=base(a,0x8C);p.add(a.s1==11);b=a
    for j,code in enumerate(restore):
        prove(p,ip(b)==code,f'sign restore dispatch{j}',False)
        before=b;out=[]
        b=ex(b,code,*keys(f'sign_restore_keys{j}'),emitted_outputs=out)
        prove(p,eq(out,before.m),f'sign restore {code:02X} no outgoing write',False)
    # Intermediate 91..9A swaps the raw data into B and back. Preservation
    # is claimed at the restored BF boundary, NOT at every intermediate A.
    prove(p,And(ip(b)==0xBF,eq([b.r[k] for k in raw],[a.r[k] for k in raw]),
                b.r[25]==a.st[24],b.r[26]==a.st[25],
                *[b.r[k]==a.st[k] for k in range(27,36)]),
          '8C/S1=B sign restore reachesBF: ALL6 raw held, '
          'R26=oldST25 and R27..35=oldST27..35; no ring write')
    before=b;out=[]
    b=ex(b,0xBF,*keys('sign_BF_keys'),emitted_outputs=out)
    prove(p,And(ip(b)==If(UGE(a.st[25],10),q['BitVecVal'](0xCE,8),q['BitVecVal'](0xC0,8)),
                eq([b.r[k] for k in raw],[a.r[k] for k in raw]),eq(out,before.m)),
          'BF entersCE IFF oldST25 is A..F; decimal0..9 entersC0')
    p.add(UGE(a.st[25],10))
    before=b;out=[]
    b=ex(b,0xCE,*keys('sign_CE_keys'),emitted_outputs=out)
    prove(p,And(ip(b)==0xCA,b.r[33]==q['N4'](9)-a.st[33],
                stack(b)[0]==0xCF,
                eq([b.r[k] for k in raw],[a.r[k] for k in raw]),eq(out,before.m)),
          'CE reachesCA, pushesCF, R33=(9-oldST33) mod16; ALL6 raw held')
    before=b;out=[]
    b=ex(b,0xCA,*keys('sign_CA_keys'),emitted_outputs=out)
    prove(p,And((ip(b)==0xDA)==(a.st[33]==10),
                (ip(b)==0xDB)==(a.st[33]!=10),b.r[26]==15,
                b.r[34]==a.st[35],stack(b)[0]==0xCF,
                eq([b.r[k] for k in raw],[a.r[k] for k in raw]),eq(out,before.m)),
          'Sign-route CA choosesDA IFF oldST33=A; header seed=oldST35, '
          'returnCF and raw6 held; no D6/EE or PC00 requirement')
    p.add(a.st[33]==10)
    entry=b;out=[]
    b=ex(b,0xDA,*keys('sign_DA_keys'),emitted_outputs=out)
    # Use the ACTUAL DA input after CE/CA. CA has adjusted the address A
    # tetras; a carry formula copied directly from the 73 entry is invalid
    # for arbitrary raw sign-route inputs. Four-bit +6 wraps before sums.
    carry0=Extract(4,4,ZeroExt(2,entry.r[28])+ZeroExt(2,entry.r[27]+q['N4'](6)))
    carry1=Extract(4,4,ZeroExt(2,entry.r[31])+ZeroExt(2,entry.r[30]+q['N4'](6))+ZeroExt(5,carry0))
    headercarry=Extract(4,4,ZeroExt(2,q['N4'](6))+ZeroExt(2,entry.r[34])+ZeroExt(5,carry1))
    header=q['N4'](6)+entry.r[34]+ZeroExt(3,carry1)+If(headercarry==0,q['N4'](10),q['N4'](0))
    prove(p,And(ip(b)==0xDC,b.r[34]==header,stack(b)[0]==0xCF,
                eq([b.r[k] for k in raw],[a.r[k] for k in raw]),eq(out,entry.m)),
          'Exact DA-input BCD carry/header formula; ALL6 raw held, '
          'no outgoing write; return remainsCF')
    p.push();p.add(a.st[35]==5)
    prove(p,Or(b.r[34]==5,b.r[34]==6),
          'Even detached nondecimal sign+selectorA with currentST35=5 '
          'produces only header5/6, NOT writer4')
    p.pop()
    # Let any source metadata produce header4; do not pretend it has been
    # constructed by keys. A positive premise must remain nonempty.
    p.add(b.r[34]==4);assert p.check()==sat
    writes=[]
    for j,code in enumerate((0xDC,0xDE,0xD4,0xDD,0xD4)):
        prove(p,ip(b)==code,f'sign header4 packet{j}',False)
        before=b;out=[]
        b=ex(b,code,*keys(f'sign_packet_keys{j}'),emitted_outputs=out)
        if code==0xD4:writes.append((out,before.m))
        else:prove(p,eq(out,before.m),f'sign packet {code:02X} no write',False)
    prove(p,And(ip(b)==0xCF,b.r[34]==4,b.s1==4,
                *[writes[0][0][k+3]==a.r[k] for k in raw],
                *[writes[1][0][k]==a.r[k] for k in raw],
                *[out[k]==page[k] for out,page in writes
                  for k in range(42) if k%3!=0 or k>=36]),
          'CONDITIONAL sign/header4 packet writes raw6 twice into M1, '
          'holds M2/M3 and returnsCF/S1=4/header4, NOT76')
    returns=runpy.run_path(str(root/'cache-d4-return-contract.py'))
    returns['c3_loop_and_cf_inlet']()
    print('CLOSED ROUTE: even with every missing sign/header field supplied, '
          'the natural CF return enters the proved endless C3 writer loop. '
          'Keys, pauses and incoming ring data cannot escape that loop. '
          'Changing the return requires ANOTHER entry/constructor.',flush=True)


def de_A_inlet():
    a=State('sign_DE_A');p=base(a,0xDE);p.add(a.r[34]==10)
    b=ex(a,0xDE,*keys('sign_DE_A_keys'))
    prove(p,ip(b)==0xDA,'Separate DE/headerA inlet forcesDA',False)
    b=ex(b,0xDA,*keys('sign_DE_A_DA_keys'))
    prove(p,And(ip(b)==0xDC,Or(b.r[34]==0,b.r[34]==1)),
          'Separate DE/headerA→DA gives header0/1, never immediate writer4')


def reader_inlet_inventory():
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
    expected={0xDA:(62,{0xDE:186,0xDD:17,0xCA:19}),
              0xCA:(19,{0x75:9,0xCE:12}),0xCE:(12,{0xBF:14})}
    for code,(count,parents) in expected.items():
        pairs=[(j,k) for j in reached if states[j][0]!=0xEE
               for k in edges[j] if states[k][0]==code]
        assert len({k for j,k in pairs})==count
        assert Counter(states[j][0] for j,k in pairs)==parents
        print('PASS completed C9/noEE cut:',f'{code:02X}',count,'contexts;',
              {f'{c:02X}':n for c,n in sorted(parents.items())},'incoming edges.',flush=True)
    pairs=[(j,k) for j in reached if states[j][0]==0xDD
           for k in edges[j] if states[k][0]==0xDA]
    assert len(pairs)==17
    assert all(states[j][2]==0xD8 and states[j][4]==0 and states[j][7]==[0]
               and states[k][3]==[10] for j,k in pairs)
    print('SCOPE: noEE after a C9 read in the completed conservative graph. '
          'Positive paths do NOT prove keyboard entry or payload transport; '
          'this is not an all-ROM predecessor claim.',flush=True)


def dd_direct_cache_loss():
    a=State('sign_DD_DA_original');other=a.copy()
    other.r[0]=q['BitVec']('sign_DD_DA_other_R0',4)
    p=base(a,0xDD);p.add(a.s1==10)
    left,right=a,other
    for j,code in enumerate((0xDD,0xDA,0xDC,0xDE)):
        prove(p,And(ip(left)==code,ip(right)==code),f'DD→DA source{j}',False)
        if code==0xDC:
            # A nonempty conditional writer-header input, NOT native flags.
            p.add(left.r[34]==4)
        before=left
        signals=keys(f'sign_DD_DA_pairkeys{j}')
        serial=State(f'sign_DD_DA_pairserial{j}').m
        out_left=[];out_right=[]
        left=ex(left,code,*signals,serial_inputs=serial,emitted_outputs=out_left)
        right=ex(right,code,*signals,serial_inputs=serial,emitted_outputs=out_right)
        prove(p,And(ip(left)==ip(right),eq(out_left,out_right),
                    eq(out_left,before.m)),
              f'DD→DA {code:02X}: identical dispatch/output, no new outgoing copy',False)
    prove(p,And(ip(left)==0xD4,
                *[eq(getattr(left,n),getattr(right,n)) for n in ('r','st','m')],
                *[getattr(left,n)==getattr(right,n) for n in ('s','s1','l','t','carry')]),
          'DD/S1=A→DA→DC/header4→DE loses originalDD.R0 completely '
          'in ALL primary fields before firstD4, without any outgoing copy')
    five=(3,9,12,18,21)
    prove(p,And(*[left.r[k-3]==a.r[k] for k in five]),
          'The other FIVE direct-cache tetras survive exactly, shifted byDD')
    writes=[]
    for j,code in enumerate((0xD4,0xDD,0xD4)):
        prove(p,ip(left)==code,f'DD five-tetra packet{j}',False)
        before=left;out=[]
        left=ex(left,code,*keys(f'sign_DD_five_packetkeys{j}'),emitted_outputs=out)
        if code==0xD4:writes.append((out,before.m))
        else:prove(p,eq(out,before.m),'DD middle step no write',False)
    prove(p,And(ip(left)==stack(a)[0],
                *[writes[0][0][k]==a.r[k] for k in five],
                *[writes[1][0][k-3]==a.r[k] for k in five],
                *[out[k]==page[k] for out,page in writes
                  for k in range(42) if k%3!=0 or k>=36]),
          'CONDITIONAL direct-DD packet exports FIVE exact tetras twice in M1, '
          'holds M2/M3 and returns its ORIGINAL tag, not forcedCF')
    print('LIMIT: R0 is one of the six DIRECT cache tetras. This tail alone '
          'cannot export all three arbitrary bytes in that layout. Earlier '
          'copies, different packing/rotation and partial recovery are NOT excluded.',flush=True)


def dd_rotated_cache_packet():
    # Detached one-position RIGHT rotation of A12, not a reference setter
    # and not an established keyboard prelude. DD then rotates LEFT once.
    a=State('sign_DD_rotated_source');entry=a.copy()
    for k in range(0,36,3):entry.r[k]=a.r[(k+33)%36]
    p=base(entry,0xDD)
    p.add(entry.s1==10,entry.r[35]==10,entry.r[26]==0,
          entry.r[37]==8,entry.r[40]==13,stack(entry)[0]==0x76)
    out=[]
    b=ex(entry,0xDD,*keys('sign_DD_rotated_entrykeys'),emitted_outputs=out)
    prove(p,And(ip(b)==0xDA,eq(b.r[0:36:3],a.r[0:36:3]),eq(out,entry.m)),
          'CONDITIONAL pre-rotation RIGHT1 thenDD restores ALL12 original A '
          'beforeDA; S1/typeA, vectorD8, R26=0 and return76 are hypotheses')
    before=b;out=[]
    b=ex(b,0xDA,*keys('sign_DD_rotated_DAkeys'),emitted_outputs=out)
    prove(p,And(ip(b)==0xDC,eq(out,before.m)),
          'Rotated-DD prefix reachesDC without a primary ring write',False)
    p.add(b.r[34]==4);assert p.check()==sat
    writes=[]
    for j,code in enumerate((0xDC,0xDE,0xD4,0xDD,0xD4)):
        prove(p,ip(b)==code,f'rotated DD packet{j}',False)
        before=b;out=[]
        b=ex(b,code,*keys(f'sign_DD_rotated_packetkeys{j}'),emitted_outputs=out)
        if code==0xD4:writes.append((out,before.m))
        else:prove(p,eq(out,before.m),f'rotated DD {code:02X} no write',False)
    prove(p,And(ip(b)==0x76,
                *[writes[0][0][k+3]==a.r[k] for k in raw],
                *[writes[1][0][k]==a.r[k] for k in raw],
                *[out[k]==page[k] for out,page in writes
                  for k in range(42) if k%3!=0 or k>=36]),
          'CONDITIONAL rotated-DD/header4 packet exports ALL6 exact raw '
          'tetras twice in M1 and returns76, holds M2/M3')
    print('LOCAL PRELUDE ONLY: need RIGHT1 AND DD/S1=typeA/header4/return76. '
          'The subsequent cache-dd-prelude-contract.py closes the direct '
          'C9→DD_A approach beforeEE/D6; prior reserves remain open. '
          'No whole-ring retention or keyboard writer follows from this packet.',flush=True)


if __name__=='__main__':
    sign_gate_and_packet()
    de_A_inlet()
    reader_inlet_inventory()
    dd_direct_cache_loss()
    dd_rotated_cache_packet()
    cases=json.loads(subprocess.check_output(
        ['node',str(root/'cache-da-sign-native.cjs'),'--proof-input'],text=True))
    recorded_sign_source(cases[0]['sourceEvents'])
    native_replays(cases)
    print('PASS sign-source and closed-return audit. No native program-cache '
          'export, no Ms transfer, no partialK2 is claimed.',flush=True)
