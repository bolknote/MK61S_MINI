#!/usr/bin/env python3
"""The ordinary A6 read helper cannot preserve DD's selector up to C8.

Its actual return tag is A7, not 2F. The closed path allows unbounded 01/02
and E5 waits, arbitrary initial R2, arbitrary keys and ring inputs.
"""
import runpy
from pathlib import Path

from z3 import And, Or, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))


def byte(lo,hi):
    return ZeroExt(4,lo)|(ZeroExt(4,hi)<<4)


def address(a):
    return byte(a.r[36],a.r[39])


def stack(a):
    return [byte(a.st[36+i],a.st[39+i]) for i in range(3)]


count = 0


def prove(ip,label,claim,condition=None):
    global count
    a = State(f'read_return_{ip}');b = execute(a,ip,*keys(f'read_return_keys_{ip}'))
    p = base(a,ip)
    if condition is not None:p.add(condition(a))
    assert p.check() == sat,label
    p.add(~claim(a,b));assert p.check() == unsat,label
    count += 1;print('PASS:',label,flush=True)


prove(0xA6,'A6 calls 01 with S1=6 and pushes the return A7',
      lambda a,b:And(address(b) == 1,b.s1 == 6,b.r[2] == a.r[2],
          *[v == w for v,w in zip(stack(b),[0xA7]+stack(a)[:2])]))
for ip,nxts in [(0x01,(1,2)),(0x02,(2,3)),(0x03,(4,)),(0x04,(0xBA,)),
                (0xBA,(0xCB,)),(0xCB,(0xDD,)),(0xDD,(0xD6,))]:
    prove(ip,f'A6 body {ip:02X}: S1=6 and the return stack are preserved',
          lambda a,b,nxts=nxts:And(b.s1 == 6,Or(*[address(b) == n for n in nxts]),
              b.r[2] == a.r[2],*[v == w for v,w in zip(stack(a),stack(b))]),
          lambda a:a.s1 == 6)
prove(0xD6,'D6 returns to the live A7 tag with R2/R38 unchanged',
      lambda a,b:And(address(b) == 0xA7,b.r[2] == a.r[2],b.r[38] == a.r[38]),
      lambda a:stack(a)[0] == 0xA7)
prove(0xA7,'A7 unconditionally enters E5 and sets S1=8, preserving R38',
      lambda a,b:And(address(b) == 0xE5,b.s1 == 8,b.r[38] == a.r[38]))
prove(0xE5,'E5 can only wait or enter E6; it preserves S1/R38/R41 and fixes S',
      lambda a,b:And(Or(address(b) == 0xE5,address(b) == 0xE6),
          b.s1 == a.s1,b.r[38] == a.r[38],b.r[41] == a.r[41],b.s == a.r[41]+12))
prove(0xE6,'E6 completes this read path through E8 with selector C/D, never 4',
      lambda a,b:And(address(b) == 0xE8,Or(b.r[38] == 12,b.r[38] == 13)),
      lambda a:And(a.s1 == 8,a.s == a.r[41]+12,Or(a.r[41] == 0,a.r[41] == 15)))
print(f'PASS: {count} local facts close the A6->DD->D6->A7 read-return family '
      'before E6 overwrites the selector. A later DD would be new preparation; '
      'no global exclusion of C8 is claimed.',flush=True)
