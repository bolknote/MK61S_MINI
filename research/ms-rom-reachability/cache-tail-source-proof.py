#!/usr/bin/env python3
"""Exact, reset-independent tail source and decoder suffix contracts.

These statements do not claim keyboard reachability of a repair. The native
reader starts ST33..35=7/F/5, so its first new four in this triple requires
R33=4 at a tail/whole push. The selector-4 reader instead starts 4/F/5.
"""
from pathlib import Path
import runpy
from z3 import And, Or, sat, unsat

root=Path(__file__).resolve().parent
q=runpy.run_path(str(root/'ik1302_symbolic.py'))
for ip in range(256):
    a=q['State'](f'cache_tail_source_{ip}')
    b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'cache_tail_source_keys_{ip}'))
    p=q['base_solver'](a,ip)
    p.add(a.r[33]!=4,*[a.st[i]!=4 for i in (33,34,35)])
    assert p.check()==sat
    p.add(Or(*[b.st[i]==4 for i in (33,34,35)]))
    assert p.check()==unsat,(ip,p.reason_unknown())
print('PASS all 256 ROM words: absent ST33/34/35=4 and R33=4, no new four '
      'can enter ST33/34/35, for arbitrary keys and serial input.',flush=True)

checker=runpy.run_path(str(root/'verify_c8_recovery_candidate.py'),
                      init_globals={'transport':{'q':q}})
decoder='35 C5 8A 65 7B B7 45 8B 48 B1 B3'
cases=[(decoder,(0xB8,0xB9)),
       (decoder+' B9 F8 FA 7A 7C',(0x76,0x77,0x78,0x79))]
for text,allowed in cases:
    sequence=[int(n,16)for n in text.split()]
    r=checker['verify_sequence'](sequence)
    assert r['result']==sat
    p=r['solver'];p.push()
    p.add(~Or(*[checker['address'](r['final'])==ip for ip in allowed]))
    assert p.check()==unsat,text
    p.pop()
    if sequence[-1]==0xB3:
        p.push();p.add(~Or(r['states'][-1].r[29]==8,r['states'][-1].r[29]==9))
        assert p.check()==unsat;p.pop()
    print('PASS arbitrary entry + physical per-tick keys + arbitrary ring:',
          text,'has next only','/'.join(f'{v:02X}'for v in allowed),flush=True)
conditional_cases=[
  ('35 45 8B 48 4A 4B',(0x4C,),
   lambda a:[Or(a.r[23]==0,a.r[23]==1)],'initial R23 in 0/1'),
  ('35 45 8B 48 4A 4C 4E 97 99 9B 9C 9E',(0x8C,),
   lambda a:[],'arbitrary entry'),
  ('35 45 8B 48 4A 4B 4C 4E 97 99 9B 9C 9E 9F AA',(0xE5,),
   lambda a:[a.r[35]==5],'initial R35=5'),
]
for text,allowed,premises,label in conditional_cases:
    r=checker['verify_sequence']([int(n,16)for n in text.split()],constraints=premises)
    assert r['result']==sat
    p=r['solver'];p.push()
    p.add(~Or(*[checker['address'](r['final'])==ip for ip in allowed]))
    assert p.check()==unsat,text
    p.pop()
    print('PASS physical per-tick keys + arbitrary ring,',label+':',text,
          'has next only','/'.join(f'{v:02X}'for v in allowed),flush=True)
print('LIMIT: only these decoder suffixes are closed; no general K2 claim.',flush=True)
