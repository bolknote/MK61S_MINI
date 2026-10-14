#!/usr/bin/env python3
"""Reset-reachable entry boundary of IK1302's exact header writer.

All serial data and untracked state are overapproximated. The only new
keyboard assumption is active rows 2..11, not a chosen key/timing sequence.
C8 is admitted any number of times; this is not a first-entry-only graph.
"""
import runpy
import sys
from pathlib import Path

root=Path(__file__).resolve().parent
sys.argv=['analyze_gates.py','--target','c7','--r38',
          '--physical-key-rows','--check-c8-invariants']
m=runpy.run_path(str(root/'analyze_gates.py'))
audit=runpy.run_path(str(root/'audit_ms_rom_control.py'))
successors,predecessors=audit['graph'](m)
print('Completed real-row superset graph:',len(successors),'states,',
      sum(map(len,successors.values())),'edges',flush=True)
for ip,expected in [(0x32,{0}),(0x34,{0x32})]:
    entries=[st for st in successors if st[0]==ip]
    actual={source[0] for target in entries for source in predecessors[target]}
    assert entries and actual==expected,(ip,actual)
    print('PASS: %02X has only reset-reachable predecessors'%ip,
          [f'{n:02X}' for n in sorted(actual)],flush=True)
zero_entries=[st for st in successors if st[0]==0]
zero_predecessors={source[0] for target in zero_entries for source in predecessors[target]}
print('Scope: the abstraction also admits incoming edges to 00:',
      [f'{n:02X}' for n in sorted(zero_predecessors)],
      '(candidate returns, not proven native keys).',flush=True)
runpy.run_path(str(root/'check_ms_header_repair.py'))
print('PASS: every 34 entry is through 00->32->34, with A all F; '
      'even a hypothetical later return to 00 cannot supply a saved header.',flush=True)
