#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const pair=require('./k1-p0-carrier-exchange.cjs');
const maker=require('./k1-logical-carrier-maker.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {MS_SLOTS,M1_SLOTS,snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const options={phaseOffset:0,carrierWord:maker.carrier,markerActions:maker.markerActions};
function makerPrefix(r) {
  const end=r.traced.events.find(e=>e.stage==='save-marker'&&e.ring);assert.ok(end);
  const rename=e=>({...e,stage:e.stage.replace(/^carrier-marker-/,'logical-carrier-')});
  return {...r,after:Object.fromEntries(MS_SLOTS.map(n=>[n,raw(end.ring[n],1,14)])),
    afterRegisters:M1_SLOTS.map(n=>raw(end.ring[n],0)),afterProgram:snapshotFromRing(end.ring).program,
    traced:{...r.traced,events:[...r.traced.events.filter(e=>e.command<end.command).map(rename),{...end,stage:'done'}],
      writes:r.traced.writes.filter(w=>w.command<end.command)}};
}
function check(r) {
  assert.deepEqual(r.options,options,'the complete endpoint contract here is the phase-zero counterexample');
  const made=maker.check(makerPrefix(r));
  const es=r.traced.events,ww=r.traced.writes,p=r.beforeRegisters[0];
  const begin=es.find(e=>e.stage==='indirect-p'&&e.ring);assert.ok(begin);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(begin.ring[n])),
    [p,r.before.V.slice(2),maker.carrier,maker.carrier]);
  assert.equal(raw(begin.ring.U,0),maker.carrier);
  const body=es.filter(e=>e.stage==='indirect-p');
  const reads=body.filter(e=>e.ip===0xD6),stores=body.filter(e=>e.ip===0xD4);
  assert.equal(reads.length,1);assert.equal(reads[0].slot,'P8');
  assert.equal(raw(reads[0].m,0),r.beforeRegisters[5]);
  assert.deepEqual(stores.map(e=>e.slot),['U','P8']);
  assert.deepEqual(stores.map(e=>raw(e.r,0)),['500700000010','000201010000']);
  // D4 uses its already rotated carrier. Reconstruct the complete output
  // from the actual twelve emitted writes instead of assuming raw(A) order.
  for(const e of stores) {
    const out=ww.filter(w=>w.command===e.command),expected=ringAt(r,e.command);
    assert.deepEqual(out.map(w=>[w.chip,w.slot,w.nibble]),
      Array.from({length:12},(_,j)=>[3,e.slot,3*j]));
    for(const w of out)expected[w.slot][w.nibble]=w.value;
    assert.deepEqual(ringAt(r,e.command+1),expected,'D4 changes only its declared twelve M1 tetras');
  }
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>i===0?r.before.V.slice(2):i===5?p:v));
  assert.deepEqual(r.after,{...r.before,U:r.before.U.slice(0,2)+'1F2'+r.before.U.slice(5),
    W:r.before.W.slice(0,2)+r.before.Q.slice(2),Q:r.before.Q.slice(0,2)+r.before.W.slice(2)});
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(ww.filter(w=>[36,37,39,40].includes(w.nibble)).every(w=>w.before===w.value));
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  const report=analyzeTrace({beforeEvent:es.find(e=>e.ring),afterEvent:es.find(e=>e.stage==='done'&&e.ring),writes:ww});
  assert.ok(report.data.missing.some(x=>x.word===r.beforeRegisters[5]),'original P5 is missing from protected outputs');
  assert.equal(report.data.sameMultiset,false);
  return {maker:made,firstPointerRead:{command:reads[0].command,actual:'P5',required:'P0'},
    normalizerWritesP0:stores[0].command,sourceWritesP5:stores[1].command,
    oldP5Missing:r.beforeRegisters[5],protectedPermutation:false,programHeld:true};
}
if(require.main===module) {
  const r=pair.run(options);console.log('PASS rejected pair after successful maker:',JSON.stringify(check(r)));
  r.traced.events.length=r.traced.writes.length=0;
}
module.exports={options,makerPrefix,check};
