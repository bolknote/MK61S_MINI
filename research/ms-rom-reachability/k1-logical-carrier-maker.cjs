#!/usr/bin/env node
'use strict';
// Construct an F7 carrier with live p/v and only the already duplicated P0
// as scratch. No hidden reads, state writes or adaptive timing in finish().
const assert=require('node:assert/strict');
const capture=require('./k1-bank-v-capture.cjs');
const retained=require('./k1-bank-marker-tail-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const carrier='0010F7000000',mask='00008F700000';
const makerKeys=[
  'Сx','+',                       // m,p,v,v -> p,v,v,v
  '1',',','8','7','В↑','1',',','7',
  'K','/-/',                     // 1.87 OR 1.7 -> 8.F7 (no stack drop)
  'X→П','0',                     // save 8.F7 in the duplicated ordinary P0
  'Сx','+','Сx','+',              // discard the two visible scratch values
  'П→X','0',                     // 8.F7,p,v,v
  'K','8',                       // fraction -> raw 9990F7000000
  'ВП','2',                      // this path adds 2 to old order -1
];
const markerActions=makerKeys.map(key=>[key]);
function finish(c,o={},record=()=>{}) {
  retained.operation(c,{...o,recoverCapture:true},record);
  for(const [i,keys] of markerActions.entries()) {
    record('logical-carrier-'+i);c.pressSequence(keys).runFrames(o.settleFrames??8);
  }
}
const run=(o={})=>capture.run(o,finish);
function check(r) {
  const es=r.traced.events,ww=r.traced.writes;
  const before=es.find(e=>e.stage==='logical-carrier-0'&&e.ring);
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(before&&end);
  const p=r.beforeRegisters[0],v=r.before.V.slice(2);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(before.ring[n])),['0000F0000000',p,v,v]);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[carrier,p,v,v]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((x,i)=>i===0?mask:x));
  assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(ww.filter(w=>w.nibble%3===0&&w.nibble<36&&w.slot!=='U')
    .every(w=>w.before===w.value),'only ordinary P0 may change');
  assert.ok(ww.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value),'all eight Ms held even transiently');
  assert.ok(ww.filter(w=>[36,37,39,40].includes(w.nibble))
    .every(w=>w.before===w.value),'all ordinary/numeric service tetras held');
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {phase:r.options.phaseOffset??0,carrier,p,v,p0Scratch:mask,
    allMsHeld:true,other14RegistersHeld:true,programHeld:true,fullExchange:false};
}
if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log('PASS logical carrier maker:',JSON.stringify(check(r)));
  r.traced.events.length=r.traced.writes.length=0;
}
module.exports={carrier,mask,makerKeys,markerActions,finish,run,check};
