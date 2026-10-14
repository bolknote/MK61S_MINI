#!/usr/bin/env python3
"""Differential check of all three symbolic ROMs against actual IK13.tick.

One arbitrary full state and per-tick key/input stream for every address of
every installed chip. These are explicitly host-seeded laboratory cases.
Compare all internal state AND all 42 outgoing serial nibbles.
"""
import json
import random
import runpy
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
first = runpy.run_path(str(root/'ik1302_symbolic.py'))
roms = json.loads(subprocess.check_output(['node','-e',
    'console.log(JSON.stringify(require(process.argv[1])))',str(first['ROM_PATH'])],text=True))
rng = random.Random(130261130306)
cases = []
for chip in ('ИК1302','ИК1303','ИК1306'):
    for ip in range(256):
        c = {'chip':chip,'ip':ip}
        for field in ('r','m','st','inputs'):
            c[field] = [rng.randrange(16) for _ in range(42)]
        c['r'][36], c['r'][39] = ip & 15, ip >> 4
        for field in ('s','s1','l','t','carry'):
            c[field] = rng.randrange(16 if field in ('s','s1') else 2)
        c['xs'] = [rng.randrange(2,12) for _ in range(42)]
        c['ys'] = [rng.choice((0,1,8,9)) for _ in range(42)]
        cases.append(c)

source = r"""
const fs = require('node:fs');
const {MK61} = require(process.argv[1]);
const calc = new MK61();
const chips = {'ИК1302':calc.ik1302,'ИК1303':calc.ik1303,'ИК1306':calc.ik1306};
const cases = JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(cases.map(c=>{
  const chip = chips[c.chip]; chip.reset();
  for (const key of ['s','s1','l','t','carry']) chip[key] = c[key];
  chip.r=c.r.slice(); chip.memory=c.m.slice(); chip.stack=c.st.slice();
  const outputs=[];
  for (let tick=0;tick<42;tick++) {
    chip.keyX=c.xs[tick]; chip.keyY=c.ys[tick]; chip.input=c.inputs[tick];
    chip.tick(); outputs.push(chip.output);
  }
  return {r:chip.r,m:chip.memory,st:chip.stack,s:chip.s,s1:chip.s1,
          l:chip.l,t:chip.t,carry:chip.carry,outputs};
})));
"""
actuals = json.loads(subprocess.check_output(['node','-e',source,
    str(first['REFERENCE_ROOT']/'tests/emulator/mk61.cjs')],input=json.dumps(cases),text=True))
models = {}
for index, (case, actual) in enumerate(zip(cases, actuals, strict=True)):
    chip = case['chip']
    if chip not in models:
        q = runpy.run_path(str(root/'ik1302_symbolic.py'))
        tables = roms[chip]
        q['execute_command'].__globals__.update(COMMANDS=tables['команды'],
            SYNCS=tables['синхропрограммы'],MICROS=tables['микрокоманды'])
        models[chip] = q
    q = models[chip]
    a = q['State'](f'differential_{index}')
    for field in ('r','m','st'):
        setattr(a,field,[q['N4'](v) for v in case[field]])
    for field in ('s','s1','l','t','carry'):
        setattr(a,field,q['N4' if field in ('s','s1') else 'N1'](case[field]))
    out = []
    b = q['execute_command'](a,case['ip'],case['xs'],[q['N4'](v) for v in case['ys']],
        serial_inputs=[q['N4'](v) for v in case['inputs']],emitted_outputs=out)
    expected = {field:[v.as_long() for v in getattr(b,field)] for field in ('r','m','st')}
    expected.update({field:getattr(b,field).as_long() for field in ('s','s1','l','t','carry')})
    expected['outputs'] = [v.as_long() for v in out]
    assert expected == actual, (chip,case['ip'],expected,actual)
    if case['ip'] == 255: print(f'PASS: {chip}, all 256 ROM addresses and 42 outputs match IK13.tick',flush=True)
print('PASS: 768 complete three-chip states, including 32,256 outgoing tetras.',flush=True)
