#!/usr/bin/env node
'use strict';
// Independently cover both native B-source entries and retained P8 in all
// three frame phases. The large roundtrip suite also exercises these blocks.
const assert=require('node:assert/strict');
const p=require('./probe_ms_zero_p0.cjs');
const {checkOne,retained}=require('./check_ms_zero_reuse.cjs');
const paths=new Set();
for(const phaseOffset of [0,1,2]) {
  const o={stress:true,sourceIndex:11,keepP8:true,phaseOffset};
  const r=p.run(o),ring=s=>r.traced.events.find(e=>e.stage===s&&e.ring).ring;
  const checked=checkOne(r,'',ring('prepare-zero-p8'),ring('done'),r.beforeRegisters[11],o);
  paths.add(checked.push);
  for(const i of [8,10])assert.equal(r.afterRegisters[i],r.beforeRegisters[i],'retained P8 or A');
  retained(r);
  console.log('PASS B-source phase',phaseOffset,'entry',checked.push,'P8/A retained; complete paths, all transfers, registers, arithmetic/program.');
}
assert.deepEqual([...paths].sort(),['P9','Z']);
console.log('PASS both B-source entries occur natively, not only in the symbolic contracts.');
