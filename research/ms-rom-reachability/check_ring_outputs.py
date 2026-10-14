#!/usr/bin/env python3
"""Artificial-state unit checks of symbolic outputs on all three ROMs.

These state assignments are deliberately a semantic differential test,
NOT a keyboard preparation or a physical-reachability experiment.
"""
import json
import random
import runpy
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
if 'headers' not in globals():
    headers = runpy.run_path(str(root / 'analyze_ring_header_writers.py'))
rng = random.Random(340213)
cases = []
for chip, emitters in headers['writers'].items():
    for ip in emitters:
        for repeat in range(3):
            c = {'chip':chip,'ip':ip}
            for group in ('r','m','st','inputs'):
                c[group]=[rng.randrange(16) for _ in range(42)]
            c['r'][36],c['r'][39]=ip%16,ip//16
            for name in ('s','s1','l','t','carry'):
                c[name]=rng.randrange(16 if name in ('s','s1') else 2)
            c['keyXs']=[rng.randrange(2,12) for _ in range(42)]
            c['keyYs']=[rng.choice([0,1,8,9]) for _ in range(42)]
            cases.append(c)
source = """
const fs=require('node:fs');
const {MK61}=require(process.argv[1]);
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
const calc=new MK61(), chips={'ИК1302':calc.ik1302,'ИК1303':calc.ik1303,'ИК1306':calc.ik1306};
const out=cases.map(c=>{
  const chip=chips[c.chip];chip.reset();
  for(const k of ['s','s1','l','t','carry'])chip[k]=c[k];
  chip.r=c.r.slice();chip.memory=c.m.slice();chip.stack=c.st.slice();
  const emitted=[];
  for(let i=0;i<42;i++){
    chip.keyX=c.keyXs[i];chip.keyY=c.keyYs[i];chip.input=c.inputs[i];
    chip.tick();emitted.push(chip.output);
  }
  return {r:chip.r,m:chip.memory,st:chip.stack,s:chip.s,s1:chip.s1,
    l:chip.l,t:chip.t,carry:chip.carry,emitted};
});
console.log(JSON.stringify(out));
"""
reference = headers['first']['REFERENCE_ROOT'] / 'tests/emulator/mk61.cjs'
actuals = json.loads(subprocess.check_output(['node','-e',source,str(reference)],
                                             input=json.dumps(cases),text=True))
for number, (c, actual) in enumerate(zip(cases,actuals)):
    model=headers['models'][c['chip']]
    a=model['State'](f'output_check_{number}')
    for group in ('r','m','st'):
        setattr(a,group,[model['N4'](n) for n in c[group]])
    for name in ('s','s1','l','t','carry'):
        setattr(a,name,model['N4' if name in ('s','s1') else 'N1'](c[name]))
    emitted=[]
    b=model['execute_command'](a,c['ip'],c['keyXs'],[model['N4'](n) for n in c['keyYs']],
        serial_inputs=[model['N4'](n) for n in c['inputs']],emitted_outputs=emitted)
    expected={group:[v.as_long() for v in getattr(b,group)] for group in ('r','m','st')}
    expected.update({name:getattr(b,name).as_long() for name in ('s','s1','l','t','carry')})
    expected['emitted']=[v.as_long() for v in emitted]
    assert expected==actual,(number,c,expected,actual)
print(f'PASS: {len(cases)} artificial complete-state/output tests across all 3 ROMs; '
      'all 42 emitted nibbles agree with the reference per case.',flush=True)
