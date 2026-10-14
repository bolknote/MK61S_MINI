#!/usr/bin/env python3
"""Complete ROM-wide classification of the R2 discriminator used by 07.

All statements use the exact 42-tick model with arbitrary keyboard and ring
signals. R[2] is an internal nibble, not user register P2.
"""
import runpy
from pathlib import Path

from z3 import And, Or, UGE, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State','execute_command','base_solver','arbitrary_keys'))

groups = {
    'zero': (0x00,0x54,0x76,0xD0,0xD1,0xD8,0xD9,0xDF),
    'eight': (0xC3,),
    'fifteen': (0x77,),
    'copy_R5': (0x58,0x78,0x7F,0x8B,0xB9),
    'copy_R1': (0x92,0x9A),
    'copy_S1': (0xB0,0xF2),
    'toggle_high_bit': (0xAF,0xC2,0xCA,0xEA),
}
labels = {ip:label for label,ips in groups.items() for ip in ips}
assert len(labels) == 23
for ip in range(256):
    a = State(f'r2_fact_{ip}');b = execute(a,ip,*keys(f'r2_fact_keys_{ip}'))
    label = labels.get(ip,'preserve')
    expected = {'zero':0,'eight':8,'fifteen':15,'copy_R5':a.r[5],
                'copy_R1':a.r[1],'copy_S1':a.s1,
                'toggle_high_bit':a.r[2]^8,'preserve':a.r[2]}[label]
    p = base(a,ip);p.add(b.r[2] != expected)
    assert p.check() == unsat, (ip,label)
    if ip in labels:
        p = base(a,ip);p.add(b.r[2] != a.r[2])
        assert p.check() == sat, (ip,'spurious writer')
    if ip == 0x07:
        p = base(a,ip)
        addr = ZeroExt(4,b.r[36])|(ZeroExt(4,b.r[39])<<4)
        p.add(~And((addr == 0x6D) == UGE(a.r[2],5),b.r[2] == a.r[2]))
        assert p.check() == unsat,'07 gate'
    if ip % 64 == 63:print(f'checked {ip+1}/256 commands',flush=True)

for label,ips in groups.items():
    print(label+': '+' '.join(f'{ip:02X}' for ip in ips),flush=True)
print('PASS: exactly 23 R2 writers, the remaining 233 commands preserve R2; '
      '07 branches to 6D iff unsigned R2>=5. In particular DD/D4/D6 do not '
      'change the mode discriminator.',flush=True)

# The first two abstract reset candidates entered L0 through this route.
# D5 is not an arbitrary program-byte fetch: its FF sentinel survives the
# whole direct 9B/9C/9E/9F route, irrespective of the number of 9B waits.
for ip in (0xD5,0x9B,0x9C,0x9E,0x9F,0xAA):
    a = State(f'd5_sentinel_{ip}');b = execute(a,ip,*keys(f'd5_sentinel_keys_{ip}'))
    p = base(a,ip)
    addr = ZeroExt(4,b.r[36])|(ZeroExt(4,b.r[39])<<4)
    if ip == 0xD5:
        claim = And(addr == 0x9B,b.r[30] == 15,b.r[33] == 15)
    elif ip == 0xAA:
        claim = Or(a.r[33] != 15,And(addr == 0xAC,b.r[35] == 15))
    else:
        claim = And(b.r[30] == a.r[30],b.r[33] == a.r[33])
        if ip == 0x9B:claim = And(claim,Or(addr == 0x9B,addr == 0x9C))
    p.add(~claim)
    assert p.check() == unsat, (ip,'D5 sentinel')
print('PASS: D5 fixes the FF sentinel; the direct 9B*/9C/9E/9F->AA route '
      'must continue to AC, never E5. This rules out that family of false '
      'L0 reset prefixes without bounding 9B waiting repetitions.',flush=True)
