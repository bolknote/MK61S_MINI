#!/usr/bin/env node
'use strict';
// Fresh keyboard-only frame diagnostic of the proposed RCL8 continuation.
// No machine-state import. This is not a full per-command write audit.
const assert=require('node:assert/strict');
const zq=require('./k1-zq-origin-entry.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const options={...JSON.parse(process.env.K1_ZQ_RESTORE_OPTIONS||'{}'),
  afterW:[['П→X','0'],['F','В↑'],['П→X','8']],afterWPhases:[0,0,0]};
const r=zq.run(options);
const start=r.rows.find(x=>x.stage==='w/tail-2');
assert.ok(start);
const original=snapshotFromRing(r.initial).words;
for(const row of r.rows.filter(x=>['immediate','done'].includes(x.stage))) {
  const expected=structuredClone(start.ring);
  const writeWord=(slot,value)=>{
    for(let j=0;j<12;j++)expected[slot][1+3*j]=parseInt(value[11-j],16);
  };
  writeWord('P9',start.registers[13]);
  writeWord('P10',start.values.P9);
  writeWord('marker',start.values.P10);
  writeWord('control',start.values.marker);
  assert.deepEqual(row.ring,expected,'only the four predicted numeric words change');
  const live=[...row.registers,...Object.values(row.ring).map(word=>raw(word))];
  assert.deepEqual(original.filter(x=>!live.includes(x)),[],'all originals, including marker/control scratch');
  assert.equal(row.values.T,start.values.T);
  assert.equal(row.values.P7,start.values.P7);
  assert.deepEqual(Object.entries(row.ring).filter(([,v])=>v[22]===15).map(([n])=>n).sort(),['Q','Z']);
}
console.log('PASS bounded RCL8 frame continuation',JSON.stringify({
  frameBoundaries:r.rows.length,originals:original.length,canonicalMissing:r.rows.at(-1).missing,
  marker:r.rows.at(-1).values.marker,control:r.rows.at(-1).values.control,
  endangersStill:['T','P7'],fullWriteAudit:false,closedExit:false}));
