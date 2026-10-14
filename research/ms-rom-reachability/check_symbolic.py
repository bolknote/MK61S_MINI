#!/usr/bin/env python3
"""Differential checks of the symbolic command model against IK13.tick."""
import json
import random
import runpy
import subprocess
from pathlib import Path

model = runpy.run_path(str(Path(__file__).with_name('ik1302_symbolic.py')))
State, execute, N4, N1 = (model[name] for name in
                        ('State', 'execute_command', 'N4', 'N1'))
randomizer = random.Random(130261)
cases = []
for round_index in range(3):
    for ip in range(256):
        case = {'ip': ip,
                'keyX': 0 if round_index == 0 else randomizer.randrange(2, 12),
                'keyY': 0 if round_index == 0 else randomizer.choice([1, 8, 9])}
        if round_index==2:
            case['keyXs']=[randomizer.randrange(2,12) for _ in range(42)]
            case['keyYs']=[randomizer.choice([0,1,8,9]) for _ in range(42)]
        for group in ('r', 'm', 'st', 'inputs'):
            case[group] = [randomizer.randrange(16) for _ in range(42)]
        case['r'][36], case['r'][39] = ip & 15, ip >> 4
        for name in ('s', 's1', 'l', 't', 'carry'):
            case[name] = randomizer.randrange(16 if name in ('s', 's1') else 2)
        cases.append(case)

source = """
const fs = require('node:fs');
const { MK61 } = require(process.argv[1]);
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const chip = new MK61().ik1302;
const out = cases.map(c => {
  chip.reset();
  for (const k of ['s','s1','l','t','carry','keyX','keyY']) chip[k]=c[k];
  chip.r=c.r.slice(); chip.memory=c.m.slice(); chip.stack=c.st.slice();
  for(let i=0;i<42;i++) {
    if(c.keyXs) {chip.keyX=c.keyXs[i];chip.keyY=c.keyYs[i];}
    chip.input=c.inputs[i];chip.tick();
  }
  return {r:chip.r.slice(),m:chip.memory.slice(),st:chip.stack.slice(),
    s:chip.s,s1:chip.s1,l:chip.l,t:chip.t,carry:chip.carry};
});
process.stdout.write(JSON.stringify(out));
"""
actuals = json.loads(subprocess.check_output(['node', '-e', source,
                    str(model['REFERENCE_ROOT'] / 'tests/emulator/mk61.cjs')],
                    input=json.dumps(cases), text=True))
for index, (case, actual) in enumerate(zip(cases, actuals)):
    state = State(f'check_{index}')
    for group in ('r', 'm', 'st'):
        setattr(state, group, [N4(n) for n in case[group]])
    for name in ('s', 's1', 'l', 't', 'carry'):
        setattr(state, name, (N4 if name in ('s', 's1') else N1)(case[name]))
    xs=case.get('keyXs',case['keyX'])
    ys=[N4(n) for n in case['keyYs']] if 'keyYs' in case else case['keyY']
    final = execute(state, case['ip'], xs, ys,
                    serial_inputs=[N4(n) for n in case['inputs']])
    expected = {group: [v.as_long() for v in getattr(final, group)]
                for group in ('r', 'm', 'st')}
    expected.update({name: getattr(final, name).as_long()
                     for name in ('s', 's1', 'l', 't', 'carry')})
    assert expected == actual, (index, case, expected, actual)
print(f'PASS: {len(cases)} complete IK1302 command states match IK13.tick')
