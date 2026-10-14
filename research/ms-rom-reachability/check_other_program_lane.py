#!/usr/bin/env python3
"""Check exact program-lane output preservation in the other two ROM chips.

The real emulator/ROM is read only. Each isolated symbolic instance uses the
corresponding chip's actual three ROM tables, with arbitrary R/M/ST and keys.
"""
import json
import runpy
import subprocess
from pathlib import Path
from z3 import Or, sat, unsat

root=Path(__file__).resolve().parent

def check(chip):
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    rom=json.loads(subprocess.check_output(['node','-e',
        'console.log(JSON.stringify(require('+json.dumps(str(q['ROM_PATH']))+')['
        +json.dumps(chip)+']))'],text=True))
    context=q['execute_command'].__globals__
    context.update(COMMANDS=rom['команды'],SYNCS=rom['синхропрограммы'],
                   MICROS=rom['микрокоманды'])
    writers=[]
    for ip in range(256):
        a=q['State'](f'{chip}_{ip}');out=[]
        q['execute_command'](a,ip,*q['arbitrary_keys'](f'keys_{chip}_{ip}'),emitted_outputs=out)
        p=q['base_solver'](a,ip)
        changed=[i for i in range(2,42,3) if not out[i].eq(a.m[i])]
        if changed:
            p.add(Or(*[out[i]!=a.m[i] for i in changed]))
            result=p.check();assert result in (sat,unsat)
            if result==sat: writers.append(ip)
        if ip%64==63: print(f'{chip}: checked {ip+1}/256',flush=True)
    print(chip,'possible program-lane writers:',[f'{ip:02X}' for ip in writers],flush=True)
    return writers

if __name__=='__main__':
    for chip in ('ИК1303','ИК1306'):
        assert check(chip) == [], chip + ': a program-lane writer exists'
    print('PASS: both other ROM chips preserve every program-lane nibble '
          'at every ROM address, with arbitrary chip states and inputs.', flush=True)
