#!/usr/bin/env python3
"""Cover every A8 entry in the completed, C8-inclusive reset abstraction.

The resulting restrictions are necessary conditions. Nonempty abstract
classes are not claimed reachable by real keys or compatible ring contents.
"""
import runpy
import sys
from pathlib import Path


def audit(m):
    control=runpy.run_path(str(Path(__file__).with_name('audit_ms_rom_control.py')))
    successors,predecessors=control['graph'](m)
    entries=[s for s in successors if s[0]==0xA8]
    outside=[(p,s) for s in entries for p in predecessors[s] if p[0]!=0xA8]
    full=[s for s in entries if 0 in s[3]]
    assert full
    assert all(s[3]==(0,) and s[1][0]==0x6E and s[2]==0x5E
               and s[5]==(2,) and 0 not in s[7] for s in full)
    gates={p for s in full for p in predecessors[s]}
    assert {s[0] for s in gates}=={0x60}
    callers={p for s in gates for p in predecessors[s]}
    assert {s[0] for s in callers}=={0x6D}
    before_call={p for s in callers for p in predecessors[s]}
    assert {s[0] for s in before_call}=={0x07,0x77}
    from77={s for s in before_call if s[0]==0x77}
    assert {p[0] for s in from77 for p in predecessors[s]}=={0x7E}
    from07={s for s in before_call if s[0]==0x07}
    assert {p[0] for s in from07 for p in predecessors[s]}=={0x06}
    print('PASS: completed graph:',len(successors),'states,',
          sum(map(len,successors.values())),'edges.',flush=True)
    print('PASS:',len(full),'full-eight A8 classes: only 60 -> A8(S1=0), '
          'return 6E, selector 2, vector 5E, nonzero marker.',flush=True)
    print('PASS: predecessor alternatives are 06 -> 07 -> 6D or '
          '7E -> 77 -> 6D; no other route reaches these full-eight classes.',flush=True)
    grouped={}
    for p,s in outside:
        grouped.setdefault(p[0],set()).update(s[3])
    print('Other A8 entries are retained, not silently discarded:',flush=True)
    for ip,selectors in sorted(grouped.items()):
        print(f'  {ip:02X}: S1='+','.join(f'{v:X}' for v in sorted(selectors)),flush=True)
    print('Only S1=0 starts eight swaps. S1=A starts three; E starts one; '
          'odd S1 never exits A8. Their abstract occurrence is not a keyboard recipe.',flush=True)
    singles=[s for s in entries if s[3]==(14,) and
             any(p[0]==0xEE for p in predecessors[s])]
    assert singles and {s[1][0] for s in singles}=={0x93,0xDD}
    assert all(s[4]==0 and s[1][1:]==(0xE5,0xA8) for s in singles)
    print('PASS:',len(singles),'EE -> single-A8 classes: R35=E; '
          'A9 can return only to 93 or DD, with E5/A8 in the other stack slots.',flush=True)
    return full,grouped


if __name__=='__main__':
    sys.argv=['analyze_gates.py','--target','c7','--r38','--check-c8-invariants']
    audit(runpy.run_path(str(Path(__file__).with_name('analyze_gates.py'))))
