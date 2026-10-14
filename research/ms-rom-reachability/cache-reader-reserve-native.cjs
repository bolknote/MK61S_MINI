#!/usr/bin/env node
'use strict';
// Compare complete native reader endpoints. Projection edits detached test
// snapshots only, never calculator state. Finite witnesses, not an exhaustive
// 256^3 keyboard theorem or global impossibility of a reserve.
const assert=require('node:assert/strict');
const {prepare}=require('./cache-d8-native.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const raw=[0,3,9,12,18,21],program=[14,17,20,23,26,29];
const cases=[fixtures[0],fixtures[1],
  {name:'all_zero',bytes:[1,2,3,0,0,0,7],keys:['1','2','3','0','0','0','7']},
  {name:'zero_zero_e0',bytes:[1,2,3,0,0,0xE0,7],
    keys:['1','2','3','0','0','K','ШГ←','0','7']},
  {name:'leading_zero',bytes:[1,2,3,0,0xD4,0xB5,7],
    keys:['1','2','3','0','K','П→X','4','K','X→П','5','7']},
  {name:'trailing_zero',bytes:[1,2,3,0xA3,0xD4,0,7],
    keys:['1','2','3','K','ПП','3','K','П→X','4','0','7']},
];

function withoutKnownPayload(snapshot) {
  const detached=structuredClone(snapshot);
  for(const j of raw)detached.ik1302.r[j]=0;
  for(const j of program)detached.ik1302.m[j]=0;
  return detached;
}

function main() {
  let common=null;
  for(const f of cases) {
    const snapshot=machineSnapshot(prepare(f,{}));
    const payload=f.bytes.slice(3,6).flatMap(v=>[v&15,v>>4]);
    assert.deepEqual(raw.map(j=>snapshot.ik1302.r[j]),payload);
    assert.deepEqual(program.map(j=>snapshot.ik1302.m[j]),payload,
      'original three codes are still in the circulating program page');
    const projected=withoutKnownPayload(snapshot);
    if(common===null)common=projected;
    else assert.deepEqual(projected,common,
      'all other R/ST/scalars and ring cells on all5 chips agree between these fixtures');
    console.log(JSON.stringify({fixture:f.name,rawBytes:f.bytes.slice(3,6),
      primaryCacheFields:raw,originalProgramFields:program,
      allOtherFiveChipFieldsEqual:true,native:true,partialK2:false}));
  }
  console.log('PASS: six native P9 reader fixtures; only A6 and the original '+
    'program M3 six tetras differ; no additional reserve in these witnesses. '+
    'LIMIT: finite fixture comparison, not every reader or prior reserve.');
}

if(require.main===module)main();
module.exports={cases,withoutKnownPayload};
