#!/usr/bin/env python3
"""Whole-ROM data-transfer and control inventory for the physical MK-61.

All 256 words of each installed ROM are inspected. Per-command checks use
arbitrary chip states, serial inputs and independently changing key pins.
This is an inventory, not a keyboard-reachability claim. JSON is written to
stdout only on request; no reference ROM or emulator state is edited.
"""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
from z3 import And, Or, ZeroExt, sat, unsat

parser=argparse.ArgumentParser()
parser.add_argument('--json',action='store_true')
args=parser.parse_args()
root=Path(__file__).resolve().parent
first=runpy.run_path(str(root/'ik1302_symbolic.py'))
roms=json.loads(subprocess.check_output(['node','-e',
    'console.log(JSON.stringify(require(process.argv[1])))',str(first['ROM_PATH'])],text=True))
results={}
models={}

def copies(p,claims):
    p.push();p.add(~And(*claims));ok=p.check()==unsat;p.pop()
    return ok

for chip in ('ИК1302','ИК1303','ИК1306'):
    q=runpy.run_path(str(root/'ik1302_symbolic.py'))
    tables=roms[chip]
    q['execute_command'].__globals__.update(COMMANDS=tables['команды'],
        SYNCS=tables['синхропрограммы'],MICROS=tables['микрокоманды'])
    models[chip]=q
    rows=[]
    for ip,word in enumerate(tables['команды']):
        a=q['State'](f'audit_{chip}_{ip:02x}');out=[]
        b=q['execute_command'](a,ip,*q['arbitrary_keys'](f'audit_keys_{chip}_{ip:02x}'),
            emitted_outputs=out)
        p=q['base_solver'](a,ip)
        assert p.check()==sat
        writes=[]
        for i in range(42):
            if out[i].eq(a.m[i]):continue
            p.push();p.add(out[i]!=a.m[i]);possible=p.check();p.pop()
            assert possible in (sat,unsat)
            if possible==sat:writes.append(i)
        forms=[]
        if copies(p,[b.r[3*i]==a.m[1+3*i] for i in range(12)]+
                     [out[1+3*i]==a.r[3*i] for i in range(12)]+
                     [out[37]==a.m[37],out[40]==a.m[40]]):
            forms.append('swap12 R0/M2')
        if copies(p,[b.r[1+3*i]==a.m[1+3*i] for i in range(14)]):
            forms.append('read14 M2->R1')
        if copies(p,[b.r[1+3*i]==a.m[2+3*i] for i in range(14)]+
                     [out[2+3*i]==a.r[1+3*i] for i in range(14)]):
            forms.append('swap14 R1/M3')
        addr=ZeroExt(4,b.r[36])|(ZeroExt(4,b.r[39])<<4)
        top=ZeroExt(4,a.st[36])|(ZeroExt(4,a.st[39])<<4)
        av=ZeroExt(4,a.r[37])|(ZeroExt(4,a.r[40])<<4)
        if copies(p,[addr==top]):following='return'
        elif copies(p,[addr==av]):following='vector R37:R40'
        else:
            p.push();following=q['possible_values'](addr,p,257);p.pop()
        old=[ZeroExt(4,a.st[36+i])|(ZeroExt(4,a.st[39+i])<<4) for i in range(3)]
        new=[ZeroExt(4,b.st[36+i])|(ZeroExt(4,b.st[39+i])<<4) for i in range(3)]
        stack='other'
        for label,expected in [('same',old),('rotate',old[1:]+old[:1]),
                ('push',[(ip&0xF0)|((ip+1)&15)]+old[:2])]:
            if copies(p,[x==y for x,y in zip(new,expected)]):stack=label;break
        row={'ip':ip,'word':word,'writes':writes,'forms':forms,'next':following,
             'stack':stack}
        rows.append(row)
        if not args.json and (forms or any(i%3==2 for i in writes) or any(i in (37,40) for i in writes)):
            print(chip,f'{ip:02X}',f'{word:06X}',forms,'write',writes,
                  'next',following,'stack',stack,flush=True)
        if not args.json and ip%64==63:print(chip,f'checked {ip+1}/256',flush=True)
    results[chip]=rows
    if not args.json:
        for lane in range(3):
            print(chip,f'M{lane+1} writers:',
                  ' '.join(f"{r['ip']:02X}" for r in rows if any(i%3==lane for i in r['writes'])),flush=True)
        print(chip,'M2 service-tetrade writers:',
              ' '.join(f"{r['ip']:02X}" for r in rows if any(i in (37,40) for i in r['writes'])),flush=True)

expected_writers = {
    'ИК1302': ({0xD4}, {0x32,0x34,0xA3,0xA8,0xBC,0xC7,0xE7,0xE9}, {0xC9}),
    'ИК1303': (set(), {0x27,0x2A,0x3A,0x4E,0xD8,0xDE}, set()),
    'ИК1306': (set(), {0xFD,0xFF}, set()),
}
for chip, lanes in expected_writers.items():
    assert len(results[chip]) == 256
    for lane, expected in enumerate(lanes):
        actual = {r['ip'] for r in results[chip] if any(i % 3 == lane for i in r['writes'])}
        assert actual == expected, (chip, lane, actual, expected)
    service = {r['ip'] for r in results[chip] if any(i in (37,40) for i in r['writes'])}
    assert service == ({0xBC} if chip == 'ИК1302' else set()), (chip, service)
assert {r['ip'] for r in results['ИК1302'] if 'swap12 R0/M2' in r['forms']} == {0xA8,0xC7,0xE7}
assert {r['ip'] for r in results['ИК1302'] if 'read14 M2->R1' in r['forms']} == {0xC8}
assert {r['ip'] for r in results['ИК1302'] if 'swap14 R1/M3' in r['forms']} == {0xC9}
if args.json:print(json.dumps(results,ensure_ascii=False))
else:print('PASS: all 768 command words checked; exact writer and transfer inventories match.',flush=True)
