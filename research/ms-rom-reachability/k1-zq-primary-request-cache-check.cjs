#!/usr/bin/env node
'use strict';
// One structurally selected phase, not a phase/key search. Passive snapshots
// show cache fragments before and shortly after A3(T), not recoverability.
const assert=require('node:assert/strict');
const probe=require('./k1-zq-origin-entry.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');

function check(r) {
  const es=r.traced.events.filter(e=>e.stage==='w/tail-2');
  const gate=es.find(e=>e.ip===0x9C&&e.nextIp===0x9E);
  const read=es.find(e=>e.ip===0xEE),reserve=es.find(e=>e.ip===0xE9);
  const request=es.find(e=>e.ip===0xA3);
  const nextGate=es.find(e=>e.command>request.command&&e.ip===0x9C);
  assert.deepEqual([gate.command,gate.slot,read.command,read.slot,reserve.command,reserve.slot,
    request.command,request.slot,nextGate.command,nextGate.slot],
  [997372,'P7',997384,'V',997388,'P8',997397,'T',997402,'P7']);
  const v=r.before.V.slice(2);
  for(const e of [gate,read,reserve,request]) {
    assert.equal(raw(e.r,1).slice(3),v.slice(3));
    for(const lane of [1,2])assert.equal(raw(e.otherChips[4].st,lane).slice(3),v.slice(3));
    for(const lane of [0,1])assert.equal(raw(e.otherChips[5].r,lane).slice(0,3),v.slice(0,3));
  }
  for(const lane of [0,1])assert.equal(raw(nextGate.otherChips[5].r,lane).slice(0,3),'142');
  return {accepted9C:[gate.command,gate.slot],requestA3:[request.command,request.slot],
    vHeaderAtRequest:v.slice(0,3),next9C:[nextGate.command,nextGate.slot],
    formerHeaderBufferNow:'142',intervalCommands:nextGate.command-request.command,
    claim:'these identified buffers only; no full-state collision or universal impossibility'};
}
if(require.main===module) {
  const r=probe.traced({afterW:[...probe.defaults.afterW,['↔']],afterWPhases:[0,0,1]});
  console.log('PASS selected request/cache trace:',JSON.stringify(check(r),null,2));
}
module.exports={check};
