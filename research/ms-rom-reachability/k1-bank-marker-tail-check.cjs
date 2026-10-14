#!/usr/bin/env node
'use strict';
// The six marker keys do not require clearing Y/Z/T first. This is a
// preserved-stack resource, not a proof of a completed one-pair exchange.
const assert=require('node:assert/strict');
const p=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const m='0000F0000000';
function marker(c,record) {
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries()) {
    record('retained-marker-'+i);c.press(k).runFrames(12);
  }
}
function operation(c,o,record) {
  const act=(s,k)=>{record(s);c.pressSequence(k).runFrames(8);};
  if(o.recoverCapture) {
    p.finish(c,o,record);
    act('recall-third',['П→X','0']);act('recall-fourth',['П→X','0']);
    act('normal-rotate-0',['F',',']);act('normal-rotate-1',['F',',']);
  } else {
    for(const k of ['3','2','1','0'])act('prefill-'+k,['П→X',k]);
  }
  marker(c,record);return c;
}
function check(r) {
  const es=r.traced.events,ww=r.traced.writes;
  const start=es.find(e=>e.stage==='retained-marker-0'&&e.ring);
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(start&&end);
  const expectedTail=r.options.recoverCapture?[r.beforeRegisters[0],r.before.V.slice(2),r.before.V.slice(2)]:
    [r.beforeRegisters[1],r.beforeRegisters[2],r.beforeRegisters[3]];
  assert.deepEqual(['Y','Z','T'].map(n=>raw(start.ring[n])),expectedTail);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[m,...expectedTail]);
  assert.ok(ww.filter(w=>w.command>=start.command&&['Y','Z','T'].includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value),'none of the six marker keys changes even a temporary tail tetra');
  assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>r.options.recoverCapture&&i===0?r.before.V.slice(2):v));
  assert.ok(ww.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1).every(w=>w.before===w.value),
    'all eight Ms unchanged even transiently');
  assert.ok(ww.filter(w=>[36,37,39,40].includes(w.nibble)).every(w=>w.before===w.value),
    'M1/M2 additional tetras unchanged');
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  if(r.options.recoverCapture) {
    const fourth=es.find(e=>e.stage==='normal-rotate-0'&&e.ring),third=es.find(e=>e.stage==='recall-fourth'&&e.ring);
    const source=r.beforeRegisters[0],v=r.before.V.slice(2);
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(third.ring[n])),[v,source,source,m]);
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(fourth.ring[n])),[v,v,source,source]);
    assert.deepEqual(Object.keys(fourth.ring).filter(n=>fourth.ring[n][22]===15),['marker']);
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(start.ring[n])),[source,source,v,v]);
  }
  return {captureReentry:!!r.options.recoverCapture,tail:expectedTail,marker:m,
    allEightMsHeld:true,otherRegistersHeld:true,programHeld:true};
}
if(require.main===module)for(const options of [{},{recoverCapture:true}]) {
  const r=p.run(options,operation);console.log('PASS marker tail:',JSON.stringify(check(r)));
  r.traced.events.length=r.traced.writes.length=0;
}
module.exports={marker,operation,check};
