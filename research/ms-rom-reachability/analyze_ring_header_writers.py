#!/usr/bin/env python3
"""Exhaustive ROM classification of writers to circulating nibble 34.

This examines hardware instructions, not calculator programs. The three
chips use separate ROM tables in separate symbolic-model namespaces.
No reset reachability is inferred from an arbitrary-state SAT result.
"""
import json
import runpy
import subprocess
from pathlib import Path
from z3 import sat, unsat

root = Path(__file__).resolve().parent
first = runpy.run_path(str(root / 'ik1302_symbolic.py'))
roms = json.loads(subprocess.check_output([
    'node', '-e', 'console.log(JSON.stringify(require(process.argv[1])))',
    str(first['ROM_PATH'])], text=True))
models, writers, results = {}, {}, {}
for chip in ('ИК1302', 'ИК1303', 'ИК1306'):
    qh = runpy.run_path(str(root / 'ik1302_symbolic.py'))
    tables = roms[chip]
    qh['execute_command'].__globals__.update(
        COMMANDS=tables['команды'], SYNCS=tables['синхропрограммы'],
        MICROS=tables['микрокоманды'])
    models[chip] = qh
    emitters = []
    for ip, command in enumerate(tables['команды']):
        # Tick 34: second sync program, j[34] = 7. Order 24 (bit 20)
        # is the sole memory/output writer. Both L branches are included.
        sync = (command >> 7) & 127
        micro = tables['синхропрограммы'][sync*9+7] & 63
        indices = [micro] if micro < 60 else [2*(micro-60)+60, 2*(micro-60)+61]
        if any(tables['микрокоманды'][n] & (1 << 20) for n in indices):
            emitters.append(ip)
    writers[chip] = tuple(emitters)
    print(chip+' possible M34 writers: '+' '.join(f'{n:02X}' for n in emitters), flush=True)
    for ip in emitters:
        a = qh['State'](f'header_{chip}_{ip}')
        emitted = []
        b = qh['execute_command'](a, ip, *qh['arbitrary_keys'](f'headerkeys_{chip}_{ip}'),
                                  emitted_outputs=emitted)
        output = emitted[34]
        p = qh['base_solver'](a, ip)
        assert p.check() == sat
        inputs = [(f'R{i}', x) for i, x in enumerate(a.r)]
        inputs += [(f'ST{i}', x) for i, x in enumerate(a.st)]
        inputs += [('M34', a.m[34]), ('S', a.s), ('S1', a.s1)]
        copy = None
        for label, expr in inputs:
            p.push()
            p.add(output != expr)
            exact = p.check() == unsat
            p.pop()
            if exact:
                copy = label
                break
        p.push()
        values = qh['possible_values'](output, p, 17)
        p.pop()
        p.push()
        p.add(output == 6)
        can6 = p.check() == sat
        p.pop()
        results[chip, ip] = {'a':a, 'b':b, 'output':output,
                             'copy':copy, 'values':values, 'can6':can6}
        print(f'  {ip:02X}: '+(copy or 'computed/conditional')+
              '; values '+','.join(f'{v:X}' for v in values)+
              ('; arbitrary-state 6 possible' if can6 else '; 6 impossible'), flush=True)
