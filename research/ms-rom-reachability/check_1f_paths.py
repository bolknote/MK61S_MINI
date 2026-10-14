#!/usr/bin/env python3
"""Exact 1F entry/exit facts and a non-physical F8/68 candidate.

The symbolic chip, reference ROM and its tick semantics are unchanged.
Every proof allows independent keyboard pins and serial input at every tick.
"""
import runpy
from pathlib import Path

from z3 import And, BitVecVal, If, Or, UGE, ULE, ULT, ZeroExt, sat, unsat

q = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, base, keys = (q[n] for n in
    ('State', 'execute_command', 'base_solver', 'arbitrary_keys'))


def byte(lo, hi):
    return ZeroExt(4, lo) | (ZeroExt(4, hi) << 4)


def address(a):
    return byte(a.r[36], a.r[39])


count = 0


def prove(ip, label, claim):
    global count
    a = State(f'one_f_fact_{count}')
    b = execute(a, ip, *keys(f'one_f_keys_{count}'))
    p = base(a, ip)
    p.add(~claim(a, b))
    assert p.check() == unsat, label
    count += 1
    print('PASS:', label, flush=True)


prove(0x1F, '1F assigns R38=R35+8, clears R32, dispatches through S1',
      lambda a, b: And(b.r[38] == a.r[35]+8, b.r[32] == 0,
                        b.s1 == a.s1, address(b) == (0x10 | ZeroExt(4, a.s1))))
prove(0x1F, '1F self-loop preserves S1=F forever; tick-level keys cannot escape it',
      lambda a, b: Or(a.s1 != 15, And(address(b) == 0x1F, b.s1 == 15)))
prove(0x4F, '4F clears S1 and preserves R35',
      lambda a, b: And(b.s1 == 0, b.r[35] == a.r[35]))
prove(0xAB, 'AB sets R26=F and takes A5 exactly for the high command nibble >=7',
      lambda a, b: And(b.r[26] == 15, b.r[32] == a.r[32], b.r[35] == a.r[35],
                        (address(b) == 0xA5) == UGE(a.r[35], 7)))
prove(0xA5, 'A5 swaps R32/R35, copies the old type into S1, then enters 1F',
      lambda a, b: And(b.r[35] == a.r[32], b.r[32] == a.r[35],
                        b.s1 == a.r[35], address(b) == 0x1F))
for ip, nxt in [(0x17,0x19), (0x19,0x1C), (0x1E,0x1C),
                (0x1A,0x18), (0x18,0x1B), (0x1B,0x1D)]:
    prove(ip, f'{ip:02X} enters {nxt:02X} without changing R26/R35/R38',
          lambda a, b, nxt=nxt: And(address(b) == nxt, b.r[26] == a.r[26],
                                    b.r[35] == a.r[35], b.r[38] == a.r[38]))
prove(0x1C, '1C selects 27 or 2D without changing R26/R35/R38',
      lambda a, b: And(Or(address(b) == 0x27, address(b) == 0x2D),
                        b.r[26] == a.r[26], b.r[35] == a.r[35], b.r[38] == a.r[38]))
prove(0x27, '27 takes 38 exactly for unsigned R26<=1; otherwise 29',
      lambda a, b: And(address(b) == If(ULE(a.r[26], 1), BitVecVal(0x38, 8),
                                        BitVecVal(0x29, 8)), b.r[26] == a.r[26]))
prove(0x2D, '2D takes 2C for nonzero R26; otherwise 2B',
      lambda a, b: address(b) == If(a.r[26] == 0, BitVecVal(0x2B, 8), BitVecVal(0x2C, 8)))
for ip in (0x14, 0x29):
    prove(ip, f'{ip:02X} enters D3, clears R26, and preserves R38',
          lambda a, b: And(address(b) == 0xD3, b.r[26] == 0, b.r[38] == a.r[38]))
for ip, nxt in [(0x10,0xE2), (0xE2,0xE5)]:
    prove(ip, f'{ip:02X} enters {nxt:02X} without changing R38',
          lambda a, b, nxt=nxt: And(address(b) == nxt, b.r[38] == a.r[38]))
prove(0xE5, 'E5 can only wait or enter E6; it preserves R38',
      lambda a, b: And(Or(address(b) == 0xE5, address(b) == 0xE6), b.r[38] == a.r[38]))
prove(0x68, '68->A5 requires selector 2 and R29 in 7..E',
      lambda a, b: Or(address(b) != 0xA5,
                      And(a.r[38] == 2, UGE(a.r[29], 7), ULE(a.r[29], 14))))
prove(0xF8, 'F8 leaves S1 only in {0,1,8,9}',
      lambda a, b: Or(*[b.s1 == n for n in (0,1,8,9)]))
prove(0xF9, 'F9 preserves S1', lambda a, b: b.s1 == a.s1)
prove(0xFC, 'FC copies S1 to R35; the numeric digit is not fetched from the ring',
      lambda a, b: b.r[35] == a.s1)
for ip in (0xF8, 0xF9, 0xFC, 0x68):
    prove(ip, f'{ip:02X} preserves R2/R26/R32/R38',
          lambda a, b: And(*[b.r[i] == a.r[i] for i in (2,26,32,38)]))

# The complete normalization/fetch island from 63, ending before CD writes
# selector 8. Waiting loops 64,01,02 can repeat arbitrarily; no depth bound.
for ip, successors in [(0x63,(0x64,)), (0x64,(0x64,0x66)), (0x66,(0x01,))]:
    prove(ip, f'{ip:02X} stays in the 63-to-CD island and preserves R38',
          lambda a,b,successors=successors: And(
              Or(*[address(b)==v for v in successors]),b.r[38]==a.r[38]))
prove(0x66, '66 fixes S1=9 on entry to the fetch helper',lambda a,b:b.s1==9)
for ip, successors in [(0x01,(0x01,0x02)), (0x02,(0x02,0x03)),
                       (0x03,(0x04,)), (0x04,(0xBA,)), (0xBA,(0xCC,)), (0xCC,(0xCD,))]:
    prove(ip, f'with S1=9, {ip:02X} stays on the fetch route, never CC->BB',
          lambda a,b,successors=successors: Or(a.s1!=9,And(
              Or(*[address(b)==v for v in successors]), b.s1==9, b.r[38]==a.r[38])))
prove(0xCC, 'CC enters BB exactly for unsigned S1>=A, otherwise CD',
      lambda a,b: address(b)==If(UGE(a.s1,10),BitVecVal(0xBB,8),BitVecVal(0xCD,8)))
prove(0x8D, '8D enters 4F exactly for unsigned S1>=A and preserves S1',
      lambda a,b: And((address(b)==0x4F)==UGE(a.s1,10),b.s1==a.s1))
prove(0x4F, '4F dispatches to (old S1):F, then clears S1',
      lambda a,b: And(address(b)==(0x0F|(ZeroExt(4,a.s1)<<4)),b.s1==0))

path_count = 0


def path(sequence, label, expected, initial=None, final=None):
    global path_count
    a = State(f'one_f_path_{path_count}')
    b = a
    p = base(a, sequence[0])
    if initial:
        p.add(initial(a))
    for i, ip in enumerate(sequence):
        b = execute(b, ip, *keys(f'one_f_path_{path_count}_keys_{i}'))
        if i+1 < len(sequence):
            p.add(address(b) == sequence[i+1])
    if final:
        p.add(final(b))
    assert p.check() == expected, label
    path_count += 1
    print('PASS:', label, flush=True)
    return a, b, p


path([0xAD,0xA5,0x1F], 'AD->A5->1F cannot supply selector 4', unsat,
     final=lambda b: b.r[38] == 4)
path([0x4F,0x1F,0x10,0xE2,0xE5], '4F->1F leads to the E5/E6 overwrite island', sat,
     final=lambda b: b.r[38] == 4)
path([0x8D,0x4F,0x2F], 'keyboard-side 8D->4F cannot dispatch to 2F', unsat)
for middle in ([0x1C], [0x19,0x1C], [0x17,0x19,0x1C], [0x1E,0x1C]):
    path([0xAB,0xA5,0x1F]+middle+[0x27,0x38],
         'ordinary AB conditional entry cannot take the short 27->38 exit: '+
         ' '.join(f'{ip:02X}' for ip in middle), unsat)

candidate = [int(s,16) for s in 'F8 F9 FC 68 A5 1F 19 1C 27 38 06 07 6D 60'.split()]
a, b, p = path(candidate, 'non-physical F8/68 candidate reaches C8 in the relaxed model', sat,
                final=lambda b: address(b) == 0xC8)
p.add(~And(a.r[38] == 2, a.r[32] == 12, a.r[26] == 1,
            UGE(a.r[2], 5), UGE(a.r[29], 7), ULE(a.r[29], 14)))
assert p.check() == unsat
print('PASS: that candidate requires initial R38=2, R32=C, R26=1, R2>=5, R29=7..E', flush=True)
print(f'PASS: {count} one-command facts, {path_count} paths and the candidate preconditions. '
      'SAT above is not reset reachability or a physical protocol.', flush=True)
