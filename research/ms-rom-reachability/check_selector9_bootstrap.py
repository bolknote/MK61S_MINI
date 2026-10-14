#!/usr/bin/env python3
"""Structural source coverage for the selector-9 bootstrap, before first C8.

The independent first-entry A3 vector bound is used explicitly. Old return
tags are treated separately, never replaced by arbitrary convenient bytes.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State,execute,base,keys = (q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))
byte = lambda lo,hi:ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)
address = lambda a:byte(a.r[36],a.r[39])
stack = lambda a:[byte(a.st[36+i],a.st[39+i]) for i in range(3)]
targets = (0x7E,0x77,0x6D,0x6F,0x60,0x06,0x07,0x62)
sources = {ip:set() for ip in targets}
pushers = {ip:[] for ip in targets}
templates = {}
for ip in range(256):
    a = State(f'nine_source_{ip}')
    b = execute(a,ip,*keys(f'nine_source_keys_{ip}'))
    p = base(a,ip)
    old,new = stack(a),stack(b)
    pushed = (ip&0xF0)|((ip+1)&15)
    for kind,expected in [('same',old),('rotate',old[1:]+old[:1]),
                          ('push',[pushed]+old[:2])]:
        p.push()
        p.add(~And(*[v==w for v,w in zip(new,expected)]))
        valid = p.check()==unsat
        p.pop()
        if valid:
            break
    else:
        raise AssertionError(('unclassified stack',ip))
    templates[ip] = a,b
    if kind=='push' and pushed in pushers:
        pushers[pushed].append(ip)
    if ip in (0xC7,0xC8):
        continue
    if ip==0xA3:
        p.add(Or(a.r[37]==a.r[40],*[byte(a.r[37],a.r[40])==n
                 for n in (0x90,0x93,0xCC,0xD3,0xD8)]))
    p.add(b.r[38]==9)
    if ip != 0x6F and kind != 'rotate':
        # Stronger than removing old copies of tag62: even with arbitrary
        # old stack contents, no same/push command supplies another entry.
        p.push()
        p.add(address(b)==0x62)
        assert p.check()==unsat, ('non-rotating hidden source of 62',ip)
        p.pop()
    for target in targets:
        p.push()
        p.add(address(b)==target,*[v!=target for v in old])
        if target==0x7E:
            p.add(b.r[35]==7)
        outcome = p.check()
        assert outcome in (sat,unsat)
        if outcome==sat:
            sources[target].add(ip)
        p.pop()
assert sources=={0x7E:{0x28},0x77:{0x7E,0xA3},0x6D:{0x07,0x77},
                 0x6F:{0x4F,0x6D,0x73},0x60:{0x6D},
                 0x06:{0x38,0x3A,0x55},0x07:{0x06},0x62:{0x6F}},sources
assert pushers=={0x7E:[0x7D],0x77:[0x76],0x6D:[],0x6F:[],0x60:[],
                 0x06:[0x05],0x07:[],0x62:[0x61]},pushers
print('PASS: all 256 source/stack forms. For selector9, type7/7E comes only '
      'from 28 or an old return; 77 from 7E/A3/return; 6D from 07/77; '
      '6F from 4F/6D/73; 60 from 6D. Only 7D/76 create return tags 7E/77.',flush=True)
print('PASS: selector9/06 has only 38/3A/55 non-return sources; 07 only '
      'comes from 06. Only 05 creates tag 06; no tag 07 can be created.',flush=True)
print('PASS: with selector9, the only non-return source of 62 is 6F, '
      'but 61 DOES create return tag 62. Its real return lifetime must '
      'be considered; it cannot be discarded as an impossible tag.',flush=True)

facts = 0


def prove(ip,label,claim):
    global facts
    a,b = templates[ip]
    p = base(a,ip)
    assert p.check()==sat
    p.add(~claim(a,b))
    assert p.check()==unsat,label
    facts += 1
    print('PASS:',label,flush=True)


prove(0x28,'28 enters 7E iff marker is nonzero and preserves type/marker/selector',
      lambda a,b:And((address(b)==0x7E)==(a.r[26]!=0),
          *[a.r[i]==b.r[i] for i in (26,35,38)]))
prove(0x7E,'7E enters 77 iff type is 7 and preserves marker/selector',
      lambda a,b:And((address(b)==0x77)==(a.r[35]==7),
          *[a.r[i]==b.r[i] for i in (26,35,38)]))
prove(0x6D,'6D enters 6F iff marker is zero, otherwise 60; preserves selector',
      lambda a,b:And((address(b)==0x6F)==(a.r[26]==0),
          (address(b)==0x60)==(a.r[26]!=0),b.r[38]==a.r[38]))
prove(0x07,'07 enters 6D iff R2>=5 and preserves marker/selector',
      lambda a,b:And((address(b)==0x6D)==UGE(a.r[2],5),
          *[a.r[i]==b.r[i] for i in (26,38)]))
prove(0x7C,'7C unconditionally replaces selector with 8',
      lambda a,b:b.r[38]==8)

a = State('nine_ad_prefix')
p = base(a,0xAD)
b = execute(a,0xAD,*keys('nine_ad_keys'))
p.add(address(b)==0xA5)
b = execute(b,0xA5,*keys('nine_a5_keys'))
p.add(address(b)==0x1F)
b = execute(b,0x1F,*keys('nine_ad_1f_keys'))
assert p.check()==sat
p.add(b.r[38]!=13)
assert p.check()==unsat
print('PASS: AD->A5->1F always prepares selector D, not9. It is not an '
      'additional selector9 source outside the AB/store/format families.',flush=True)
a,b = templates[0x1F]
p = base(a,0x1F)
p.add(a.s1==15)
assert p.check()==sat
p.add(~And(address(b)==0x1F,b.s1==15))
assert p.check()==unsat
print('PASS: the 1F self-loop cannot escape for any number of repetitions.',flush=True)
print(f'PASS: {facts} universal facts. Combine with the completed reset '
      'projection and prior type7 theorem; this is not a physical protocol.',flush=True)
