#!/usr/bin/env node
'use strict';
// Negative controls for an X-only load: key 2 selects the wrong physical
// source; key 8 reaches P2 and loads X, but its formatter also writes P8.
const assert=require('node:assert/strict');
const p=require('./probe_ms_clone_load_x.cjs');
const {checkClones,release}=require('./check_ms_marker_clone_w.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const marker='0000F0000000',g='958912345678',zero='000000000000';
const upper=['P7','P8','P9','P10'];
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q',...upper];
function check(r,key=r.options.sourceKey??'8') {
  assert.ok(['2','8'].includes(key));const k=Number(key),es=r.traced.events;
  const entries=checkClones(r);assert.equal(entries.length,1);
  assert.equal(r.result.stoppedOnGuard,true);assert.equal(r.options.phaseOffset,2);
  const stage=es.find(e=>e.stage.startsWith('clone-load-')&&e.ip===0xD6)?.stage;assert.ok(stage);
  const begin=es.find(e=>e.stage===stage&&e.ring);assert.ok(begin);
  assert.deepEqual(['X','Y','Z','T','U','V','W','Q'].map(n=>raw(begin.ring[n])),
    [marker,marker,zero,g,g,g,marker,g]);
  for(const n of upper)assert.equal(raw(begin.ring[n]),r.before[n].slice(2));
  assert.ok(r.traced.writes.filter(w=>w.command<begin.command&&upper.includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value));
  const at=es.findIndex(e=>e.stage===stage&&e.ip===1);
  const seq=[1,1,1,...Array(k+1).fill(2),3,4,0xBA,0xCB,0xDD,0xD6];
  const path=es.slice(at,at+seq.length);
  assert.deepEqual(path.map(e=>[e.ip,e.slot]),seq.map((ip,i)=>[ip,slots[(7+i)%15]]));
  assert.ok(path.every((e,i)=>e.command===path[0].command+i));
  assert.equal(path[0].r[32],k);assert.equal(path[2].slot,'W');assert.equal(path[2].raw,marker);
  const physical=(k+9)%15,source=r.beforeRegisters[physical],read=path.at(-1);
  assert.equal(read.slot,slots[(physical+7)%15]);assert.equal(raw(read.m,0),source);
  const pushAt=es.findIndex(e=>e.stage===stage&&e.command>read.command&&e.ip===0xE7);
  const push=checkSwapBlock(r,pushAt,4);
  assert.deepEqual(push.body.map(e=>e.slot),key==='8'?['X','Y','Z','T']:['P8','P9','P10','marker']);
  assert.equal(raw(push.body[0].r,0),source);
  const returnAt=es.findIndex(e=>e.stage===stage&&e.command>push.body.at(-1).command&&e.ip===0xE7);
  const returned=checkSwapBlock(r,returnAt,1);assert.equal(returned.body[0].slot,'P8');
  assert.equal(raw(returned.body[0].r,0),key==='8'?source:g);
  assert.equal(r.after.P8.slice(2),key==='8'?source:g);
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  if(key==='8') {
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[source,marker,marker,zero]);
    for(const n of upper.filter(n=>n!=='P8'))assert.equal(r.after[n],r.before[n]);
    assert.equal(returned.body[0].raw,r.before.P8.slice(2));assert.equal(r.traced.display,'103,');
  } else {
    assert.equal(r.after.P7,r.before.P7);assert.equal(r.after.P9.slice(2),r.before.P8.slice(2));
    assert.equal(r.after.P10.slice(2),r.before.P9.slice(2));assert.equal(r.traced.display,'-1,2345678-42');
  }
  assert.deepEqual(['U','V','W','Q'].map(n=>r.after[n].slice(2)),[g,g,marker,g]);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>[6,10,14].includes(i)?marker:v));
  return {key,physical:physical.toString(16).toUpperCase(),source,load:push.body[0].command,
    writes:push.body.map(e=>e.slot),formatterWritesSixth:returned.body[0].command,display:r.traced.display};
}
function main() {
  for(const sourceKey of (process.env.MS_CLONE_LOAD_KEY?[process.env.MS_CLONE_LOAD_KEY]:['2','8'])) {
    const r=p.run({phaseOffset:2,sourceKey});console.log('PASS rejected X-only continuation:',JSON.stringify(check(r)));release(r);
  }
}
if(require.main===module)main();
module.exports={check};
