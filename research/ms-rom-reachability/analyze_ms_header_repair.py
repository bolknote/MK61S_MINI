#!/usr/bin/env python3
"""Incoming edges of the exact three-tetra header writer, at arbitrary state.

SAT edges are candidates only, not native keyboard reachability.
"""
import runpy
from pathlib import Path
from z3 import Or, ZeroExt, sat, unsat
q=runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
addr=lambda a:ZeroExt(4,a.r[36])|(ZeroExt(4,a.r[39])<<4)
for ip in range(256):
    a=q['State']('header_pred_'+str(ip));b=q['execute_command'](a,ip,*q['arbitrary_keys']('header_keys_'+str(ip)))
    p=q['base_solver'](a,ip);p.add(Or(addr(b)==0x32,addr(b)==0x34))
    if p.check()==sat:
        print('%02X ->'%ip,[f'{n:02X}' for n in q['possible_values'](addr(b),p,3)],flush=True)
    if ip%64==63:print('checked',ip+1,'/256',flush=True)
