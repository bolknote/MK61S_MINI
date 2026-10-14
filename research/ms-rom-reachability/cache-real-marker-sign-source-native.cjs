#!/usr/bin/env node
'use strict';
// Observe a genuine F sign source: the real M2 marker displaced by an
// already keyboard-only upper push. This SEPARATE K1 geometry changes Ms
// and ordinary P0. It is not a preserving preparation of the C8 inlet.
// No diagnostic assigns a register, memory cell, ROM word or core flag.
const assert=require('node:assert/strict');
const cap=require('./k1-bank-v-capture.cjs');
const zw=require('./k1-zw-entry.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const options={...zw.defaults,afterW:[['П→X','0']],afterWPhases:[0]};

function finish(c,record=()=>{}) {
  zw.finish(c,options,record);c.runFrames(3);aligned(c);
}

function capture({mirror=true,log=true}={}) {
  const c=cap.prepare(options),before={ms:fullMsPages(c),registers:registers(c),program:program(c)};
  let stage='',started=false,ended=false;
  const prefix=[];
  const t=trace(c,c=>finish(c,s=>{stage=s;}),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:()=>stage==='w/tail-0',
    otherChipsAt:e=>{
      if(stage!=='w/tail-0'||ended)return false;
      if(e.ip===0xA9&&e.slot==='control')started=true;
      if(started)prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      if(started&&e.ip===0xE3)ended=true;
      return false;
    },
    ringAt:e=>[0xE7,0xA8,0xA9,0xEE].includes(e.ip),
  });
  const es=t.events,start=es.findIndex(e=>e.ip===0xA9&&e.slot==='control');
  assert.ok(start>=4,'the upper push really straddles the real marker');
  const push=es.slice(start-4,start),sourceEvents=es.slice(start,start+9);
  assert.deepEqual(push.map(e=>[e.ip,e.slot]),
    [[0xE7,'P8'],[0xA8,'P9'],[0xA8,'P10'],[0xA8,'marker']]);
  assert.deepEqual(sourceEvents.map(e=>e.ip),[0xA9,0xAC,0xE2,0xE5,0xE5,0xE6,0xED,0xEE,0xE3]);
  assert.ok(sourceEvents.every((e,i)=>!i||e.command===sourceEvents[i-1].command+1));
  assert.equal(raw(push[3].ring.marker),'000FFFFFFFFF');
  assert.equal(raw(sourceEvents[0].r,0),'000FFFFFFFFF');
  assert.equal(sourceEvents[0].r[24],15,'the displaced real marker has a genuine signF');
  assert.equal(sourceEvents[0].ring.Y[24],0,'ordinary PC still has sign0');
  assert.equal(raw(sourceEvents[2].r,0),'F42FFFFFFFFF','AC changes the address fields, not signF');
  assert.equal(sourceEvents[7].slot,'V');
  assert.equal(raw(sourceEvents[8].r,0),'042931415926','EE replaces A with the numeric V word');
  assert.equal(sourceEvents[8].r[24],9);
  assert.ok(sourceEvents.every(e=>e.st[25]===0),'the marker F never becomes saved signST25 here');
  assert.equal(prefix.length,sourceEvents.length);
  const after={ms:fullMsPages(c),registers:registers(c),program:program(c)};
  assert.deepEqual(after.program,before.program);
  assert.equal(after.registers[12],before.registers[12]);
  assert.notDeepEqual(after.ms,before.ms,'this source diagnosis uses a changed K1 bank');
  if(mirror) {
    const plain=cap.prepare(options);
    fullMsPages(plain);registers(plain);program(plain);finish(plain);
    fullMsPages(plain);registers(plain);program(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh unobserved ALL5 mirror');
  }
  const report={sourceWord:'000FFFFFFFFF',sourceSign:15,
    source:'real M2 marker displaced by upper E7/A8 push',
    path:sourceEvents.map(e=>e.ip),beforeEE:'F42FFFFFFFFF',afterEE:'042931415926',
    signAfterEE:9,savedSignThroughout:0,ordinaryPCSignFCreated:false,
    all105ProgramBytesHeld:true,MsChanged:true,
    changedMsSlots:Object.keys(before.ms).filter(n=>before.ms[n]!==after.ms[n]),
    changedOrdinaryRegisters:before.registers.flatMap((v,i)=>v===after.registers[i]?[]:[i]),
    observerIndependent:mirror,preservingC8Preparation:false,programCacheExport:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,sourceEvents,prefix,before,after};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(capture({mirror:false,log:false})));
  else {
    capture();
    console.log('PASS native real-marker signF source and fresh ALL5 mirror; '
      +'EE replaces it before any D4. The separate K1 source geometry changes Ms/P0.');
  }
}
module.exports={options,finish,capture};
