#!/usr/bin/env python3
"""Partial-K2 obligations: control closure, buffer clobber, and a byte reader.

The cache establishes reset-controller constraints, not positive reachability.
The universal byte-reader theorem is conditional on one native continuation
and its recorded incoming ring stream. It is not a global information-loss
theorem, a callable six-byte swap, or a prohibition on repeated byte reads.
"""
import gzip
import json
from pathlib import Path
import runpy
import subprocess

from z3 import And, Or, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
State,execute,base,keys=(q[n] for n in
                       ('State','execute_command','base_solver','arbitrary_keys'))
byte=lambda lo,hi:q['ZeroExt'](4,lo)|(q['ZeroExt'](4,hi)<<4)
address=lambda a:byte(a.r[36],a.r[39])


def prove(p,claim,label):
    assert p.check()==sat,('inconsistent premises',label)
    p.push();p.add(~claim)
    assert p.check()==unsat,label
    p.pop();print('PASS:',label,flush=True)


def reset_entries():
    audit=runpy.run_path(str(root/'k1-formatter-entry-audit.py'))
    with gzip.open(audit['cache_path'],'rt',encoding='utf8') as stream:data=json.load(stream)
    metadata=data['metadata']
    assert metadata['sourceSha256']==audit['fingerprints'](),'changed cache inputs'
    assert metadata['complete'] and metadata['pending']==0 and metadata['terminal'] is None
    assert metadata['argv']==audit['argv']
    states=data['states'];edges=data['successors']
    assert len(states)==len(edges)==len(data['parents'])
    assert all(0<=i<len(states) for row in edges for i in row)
    ids=data['indexes']['byIp']['C9']
    assert ids
    returns={states[j][0] for i in ids for j in edges[i]}
    assert returns=={0x06,0x67},returns
    assert all(states[i][5] is not None and set(states[i][5])=={8} for i in ids)
    print(f'PASS: completed reset overapproximation: {len(ids)} C9 contexts; '
          'returns only 06/67, all with R38=8 (not EC).',flush=True)


def c9_island():
    # Unlike the older C8 theorem, R26 is unrestricted, so both the read FE
    # and program-edit F9 cases are covered. No first-entry lemma is used.
    island={
        0x67:({0x6A},None,{9}),0x6A:({0x6B},{8,9},{8,9}),
        0x6B:({0x6C},{8,9},{8,9}),0x6C:({0x68,0x69},{8,9},{8,9}),
        0x69:({0x6A,0xFB},{8,9},{8,9}),0x68:({0x05,0x69},{8,9},{8,9}),
        0xFB:({0xFC,0xFD},None,None),0xFD:({0xF9,0xFE},None,None),
        0xF9:({0xFC},None,None),0xFE:({0xFC},None,None),
        0xFC:({0x68},None,{8}),
    }
    for ip,(targets,selectors,next_selectors) in island.items():
        a=State(f'partial_island_{ip:02x}');out=[]
        b=execute(a,ip,*keys(f'partial_island_keys_{ip:02x}'),emitted_outputs=out)
        p=base(a,ip);p.add(a.r[38]==8)
        if selectors is not None:p.add(Or(*[a.s1==v for v in selectors]))
        claim=And(Or(*[address(b)==v for v in targets]),b.r[26]==a.r[26],b.r[38]==8,
                  *[out[i]==a.m[i] for i in range(42)],
                  *[b.st[i]==a.st[i] for i in (36,37,38,39,40,41)])
        if next_selectors is not None:claim=And(claim,Or(*[b.s1==v for v in next_selectors]))
        prove(p,claim,f'{ip:02X}: closed program-buffer island, R26 unrestricted; '
              'no IK1302 ring write')
    helper={0x01:{0x01,0x02},0x02:{0x02,0x03},0x03:{0x04},0x04:{0xBA},
            0xBA:{0xCC},0xCC:{0xCD},0xCD:{0xC9}}
    for ip,targets in helper.items():
        a=State(f'partial_helper_{ip:02x}');out=[]
        b=execute(a,ip,*keys(f'partial_helper_keys_{ip:02x}'),emitted_outputs=out)
        p=base(a,ip);p.add(a.s1==9,a.r[38]==8)
        prove(p,And(b.s1==9,b.r[38]==8,Or(*[address(b)==v for v in targets]),
                    *[out[i]==a.m[i] for i in range(42)]),
              f'{ip:02X}: selector-9 helper cannot reach EC or a primary Ms writer')
    a=State('partial_helper_start');out=[]
    b=execute(a,0x05,*keys('partial_helper_start_keys'),emitted_outputs=out)
    p=base(a,0x05);p.add(a.r[38]==8)
    prove(p,And(address(b)==1,b.s1==9,b.r[38]==8,
                byte(b.st[36],b.st[39])==6,*[out[i]==a.m[i] for i in range(42)]),
          '05 starts that helper with return 06, without a ring write')


def ec_clobber():
    a=State('partial_ec');out=[]
    b=execute(a,0xEC,*keys('partial_ec_keys'),emitted_outputs=out)
    prove(base(a,0xEC),And(*[b.r[3*i]==a.r[1+3*i] for i in range(12)],
                          *[b.r[1+3*i]==a.r[3*i] for i in range(12)],
                          byte(b.r[37],b.r[40])==0x3E,
                          *[out[i]==a.m[i] for i in range(42)]),
          'EC swaps the numeric 12-tetra buffers but replaces B service byte by 3E; '
          'it is not a transparent 14-tetra bridge')


def buffer_bridges():
    copiers=[];transparent=[]
    for ip in range(256):
        a=State(f'partial_bridge_{ip}');out=[]
        b=execute(a,ip,*keys(f'partial_bridge_keys_{ip}'),emitted_outputs=out)
        p=base(a,ip)
        p.push();p.add(b.r[0]!=a.r[1]);candidate=p.check()==unsat;p.pop()
        if not candidate:continue
        claim=And(*[b.r[3*i]==a.r[1+3*i] for i in range(12)])
        p.push();p.add(~claim);whole=p.check()==unsat;p.pop()
        if not whole:continue
        copiers.append(ip)
        p.push();p.add(Or(b.r[37]!=a.r[37],b.r[40]!=a.r[40]))
        held=p.check()==unsat;p.pop()
        if held:transparent.append(ip)
    assert copiers==[0x16,0x3F,0x49,0x91,0x98,0xE1,0xEC],copiers
    assert transparent==[0x98],transparent
    print('PASS: all 256 words audited; complete unconditional B->A copiers:',
          ' '.join(f'{ip:02X}' for ip in copiers),'; only 98 preserves both B service tetras.',
          flush=True)
    a=State('partial_bridge_98_exact');out=[]
    b=execute(a,0x98,*keys('partial_bridge_98_exact_keys'),emitted_outputs=out)
    prove(base(a,0x98),And(*[b.r[3*i]==a.r[1+3*i] for i in range(12)],
                          *[b.r[1+3*i]==a.r[3*i] for i in range(12)],
                          b.r[37]==a.r[37],b.r[40]==a.r[40],address(b)==0x9A,
                          *[out[i]==a.m[i] for i in range(42)]),
          '98 is an exact service-preserving numeric A/B swap and continues at 9A; '
          'no native program-buffer inlet is asserted')
    before=b;out9a=[]
    b=execute(b,0x9A,*keys('partial_bridge_9a_exact_keys'),emitted_outputs=out9a)
    prove(base(a,0x98),And(*[b.r[3*i]==a.r[1+3*i] for i in range(12)],
                          *[b.r[1+3*i]==a.r[2+3*i] for i in range(12)],
                          *[b.r[2+3*i]==a.r[3*i] for i in range(12)],
                          b.r[37]==a.r[37],b.r[40]==a.r[40],
                          *[out9a[i]==before.m[i] for i in range(42)],
                          address(b)==byte(a.st[36],a.st[39])),
          'natural 98->9A is a THREE-buffer rotation (A,B,C)->(B,C,A), '
          'not a callable A/B swap; it preserves B service and returns via ST')


def program_byte():
    native=json.loads(subprocess.check_output(
        ['node',str(root/'check_partial_k2_program_byte.cjs'),'--proof-input'],text=True))
    events=native['events'];first=events[0]
    assert events[-2]['ip']==0xC9 and events[-1]['ip']==0x06
    assert events[0]['slot']==events[-2]['slot']=='Y'
    a=State('partial_byte_entry');p=base(a,0xC9)
    # Full concrete control context from ordinary keys; the program packet is
    # free. No such state is ever assigned to the native calculator.
    for field in ('r','st'):
        p.add(*[v==q['N4'](n) for v,n in zip(getattr(a,field),first[field])])
    p.add(*[a.m[i]==q['N4'](n) for i,n in enumerate(first['m']) if i%3!=2])
    for field in ('s','s1','l','t','carry'):
        p.add(getattr(a,field)==first[field])
    other=a.copy();alternative=State('partial_other_program')
    for i in range(14):
        if i not in native['selectedPacketTetras']:
            other.m[2+3*i]=alternative.m[2+3*i]
    b,c=a,other;last_out=[]
    for i,e in enumerate(events[:-1]):
        serial=[q['N4'](n) for n in events[i+1]['m']]
        signal=keys(f'partial_byte_keys_{i}')
        outgoing=[];before=b
        b=execute(b,e['ip'],*signal,serial_inputs=serial,emitted_outputs=outgoing)
        c=execute(c,e['ip'],*signal,serial_inputs=serial)
        prove(p,And(address(b)==events[i+1]['ip'],address(c)==events[i+1]['ip']),
              f'program-byte path {i+1}/{len(events)-1}: {e["ip"]:02X} forced; '
              'all 14 program tetras and per-tick key pins free')
        if i not in (0,len(events)-2):
            prove(p,And(*[outgoing[j]==before.m[j] for j in range(42)]),
                  f'program-byte path {i+1}: no primary memory write')
        last_out=outgoing
    prove(p,And(b.r[30]==a.m[26],b.r[33]==a.m[29],
                *[b.r[1+3*i]==a.r[1+3*i] for i in range(14)],
                *[last_out[2+3*i]==a.m[2+3*i] for i in range(14)]),
          'the pair restores all seven program bytes and scratch B; '
          'only selected program byte 89 is copied to A[10:12]')
    # At the immediate C9 return S still contains a nibble from the program
    # vector. Do NOT claim full-state independence before this scratch residue
    # is discarded by the natural successor 06.
    scratch_sources=[]
    for i in range(14):
        p.push();p.add(b.s!=a.m[2+3*i])
        if p.check()==unsat:scratch_sources.append(i)
        p.pop()
    assert len(scratch_sources)==1,scratch_sources
    print('PASS: immediate C9 scratch S retains program packet tetra',
          scratch_sources[0],'; it is not a second stable byte cache.',flush=True)
    prove(p,And(*[x==y for field in ('r','m','st')
                  for x,y in zip(getattr(b,field),getattr(c,field))]),
          'with byte 89 fixed, all R/M/ST agree immediately after paired C9')
    serial=State('partial_post_pair_serial').m;signal=keys('partial_post_pair_06_keys')
    b=execute(b,0x06,*signal,serial_inputs=serial)
    c=execute(c,0x06,*signal,serial_inputs=serial)
    prove(p,And(address(b)==7,address(c)==7,
                *[x==y for field in ('r','m','st')
                  for x,y in zip(getattr(b,field),getattr(c,field))],
                *[getattr(b,n)==getattr(c,n) for n in ('s','s1','l','t','carry')]),
          'after the forced 06, every other program byte may vary independently '
          'without changing any IK1302 field on this continuation')
    print('LIMIT: the original other six bytes remain in program memory; '
          'this is no global information-loss or partial-K2 impossibility theorem.',flush=True)


def three_byte_reader():
    native=json.loads(subprocess.check_output(
        ['node',str(root/'check_partial_k2_program_scan.cjs'),'--proof-input'],text=True))
    events=native['events'];first=events[0]
    assert first['ip']==0xC9 and events[-1]['ip']==0x33
    a=State('partial_scan_entry');p=base(a,0xC9)
    for field in ('r','st'):
        p.add(*[v==q['N4'](n) for v,n in zip(getattr(a,field),first[field])])
    p.add(*[a.m[i]==q['N4'](n) for i,n in enumerate(first['m']) if i%3!=2])
    for field in ('s','s1','l','t','carry'):p.add(getattr(a,field)==first[field])
    original=[a.m[2+3*i] for i in range(14)]
    b=a;parked=False;swaps=0
    for i,e in enumerate(events[:-1]):
        if e['ip']==0xC9:
            assert e['slot']==native['programSlot']
            parked=not parked;swaps+=1
        # Couple every return of the ORIGINAL program packet through the ring,
        # not just its first appearance. During a C9 parking interval the
        # packet contains concrete scratch B, proved below on each write.
        serial=[q['N4'](n) for n in events[i+1]['m']]
        if events[i+1]['slot']==native['programSlot'] and not parked:
            for j in range(14):serial[2+3*j]=original[j]
        before=b;out=[]
        b=execute(b,e['ip'],*keys(f'partial_scan_keys_{i}'),
                  serial_inputs=serial,emitted_outputs=out)
        # Accumulate universal edge obligations rather than logging hundreds
        # of redundant PASS lines. A bad edge fails at its precise index.
        p.push();p.add(address(b)!=events[i+1]['ip'])
        assert p.check()==unsat,('scan edge',i,e['ip'],events[i+1]['ip'])
        p.pop()
        if e['ip']==0xC9:
            expected=[q['N4'](e['r'][1+3*j]) for j in range(14)] if parked else original
            prove(p,And(*[out[2+3*j]==expected[j] for j in range(14)],
                        *[out[j]==before.m[j] for j in range(42) if j%3!=2]),
                  f'scan C9 {swaps}/6: '+('only parks concrete scratch; original stays in B'
                   if parked else 'returns the entire arbitrary original program packet'))
        else:
            p.push();p.add(Or(*[out[j]!=before.m[j] for j in range(42)]))
            assert p.check()==unsat,('scan non-C9 writer',i,e['ip'])
            p.pop()
    assert swaps==6 and not parked
    prove(p,And(*[b.r[9*i]==original[4+2*i] for i in range(3)],
                *[b.r[9*i+3]==original[5+2*i] for i in range(3)],
                *[b.r[9*i+6]==15 for i in range(3)]),
          f'{len(events)-1} forced steps: all three raw bytes 87..89 coexist at 33, '
          'with F separators; no numerical conversion or primary Ms write')
    for ip in (0x33,0x35):
        wait=State(f'partial_scan_wait_{ip}');after=execute(wait,ip,*keys(f'partial_scan_wait_keys_{ip}'))
        claim=And(*[after.r[i]==wait.r[i] for i in (0,3,6,9,12,15,18,21,24)])
        prove(base(wait,ip),claim,f'{ip:02X}: all three raw byte slots and separators survive; '
              'this local preservation theorem does not choose the exit branch')
    print('LIMIT: fixed native entry and incoming non-program ring stream; '
          'not a callable byte-to-Ms writer, arbitrary source address, or partial K2.',flush=True)


if __name__=='__main__':
    reset_entries();c9_island();ec_clobber();buffer_bridges();program_byte();three_byte_reader()
