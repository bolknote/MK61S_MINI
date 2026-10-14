#!/usr/bin/env node
'use strict';
// ROM-directed controls, not a key search. DA and recall are real keys;
// passive tracing and fresh mirrors distinguish a native type7 from a
// hypothetical early T header. No calculator state setters are permitted.
const assert=require('node:assert/strict');
const {prepare,finish}=require('./cache-da-keyboard.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const registers=c=>Array.from({length:15},(_,i)=>rawMemoryRegister(c,i));
function working(c) {
  assert.equal(c.ir2a.tickIndex,84);
  const parts={X1:c.ik1306.memory,X:c.ik1303.memory,Y:c.ik1302.memory,
    Z:c.ir2b.memory.slice(84,126),T:c.ir2b.memory.slice(126,168)};
  return Object.fromEntries(Object.entries(parts).map(([slot,m])=>[
    slot,Array.from({length:12},(_,i)=>m[34-3*i].toString(16).toUpperCase()).join(''),
  ]));
}
function ready() {
  const c=prepare();finish(c);aligned(c);
  assert.equal(rawMemoryRegister(c,3),'79090FFFFFFE');
  assert.equal(rawMemoryRegister(c,5),'F79090FFFFFF');
  return c;
}
function run(keys) {
  const c=ready(),before={program:listing(c),ms:fullMsPages(c),registers:registers(c)};
  const recall=trace(c,c=>{c.pressSequence(['П→X','3']);aligned(c);},{
    extraIps:[0xD6,0xE7,0xD7],fullState:true,
  });
  assert.equal(working(c).X,'79090FFFFFFE','P3 becomes a real native M2 type7 in X');
  assert.ok(recall.events.some(e=>e.ip===0xD6&&e.slot==='Q'));
  assert.ok(recall.events.some(e=>e.ip===0xE7&&e.slot==='X'));
  assert.ok(recall.events.some(e=>e.ip===0xEE&&e.raw[0]==='7'));
  assert.deepEqual(listing(c),before.program,'the recall itself holds all105 program bytes');
  assert.deepEqual(fullMsPages(c),before.ms);
  assert.deepEqual(registers(c),before.registers);
  const source=working(c);
  const continuation=trace(c,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:[0xD6,0xE7,0xD7],fullState:true,
  });
  assert.deepEqual(working(c),source,'the selected control does not move the type7 word');
  assert.ok(continuation.events.some(e=>e.ip===0xD7),'selected control takes D7');
  const programChanges=listing(c).flatMap((value,address)=>value===before.program[address]?[]:
    [{address,before:before.program[address],after:value}]);
  assert.deepEqual(fullMsPages(c),before.ms);
  assert.deepEqual(registers(c),before.registers);
  const plain=ready();plain.pressSequence(['П→X','3']);aligned(plain);
  plain.pressSequence(keys);aligned(plain);
  assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh unobserved ALL5 mirror');
  console.log(JSON.stringify({keys,nativeRecallX:source.X,workingUnmoved:true,
    ordinary15Held:true,program105Held:programChanges.length===0,programChanges,
    Ms56Held:true,observerIndependent:true,
    noEarlyTConstructor:true,partialK2:false}));
}
if(require.main===module) {
  for(const keys of [['В↑'],['↔'],['F','↔'],['F','В↑']])run(keys);
  console.log('PASS native type7 via DA→P3→recallX; four fixed D7 transfer controls '
    +'and four fresh ALL5 mirrors. Not all type7 contexts or keys are excluded.');
}
module.exports={ready,working,run};
