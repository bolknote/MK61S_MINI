#!/usr/bin/env node
'use strict';
// Three physical frame phases of the same ROM-directed digit control.
// Offsets are applied INSIDE the passive trace, never aligned away before it.
const assert=require('node:assert/strict');
const {prepareReader}=require('./cache-da-sign-native.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {layout}=require('./cache-d4-native-topology.cjs');
const raw=[0,3,9,12,18,21],suffix=['F','Сx','1'];
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const spec={fixture:fixtures[1],selector:10,carrier:'0'};
function finish(c,phase) {c.runFrames(phase).pressSequence(suffix);aligned(c);}

function capture(phase,{mirror=true,log=true}={}) {
  assert.ok([0,1,2].includes(phase));
  const {c,program,ms,payload}=prepareReader(spec);
  const entries=[];let collecting=false;
  const t=trace(c,c=>finish(c,phase),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    otherChipsAt:e=>{
      if(e.ip===0x8C&&!entries.length)collecting=true;
      if(collecting&&entries.length<65)
        entries.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
  });
  assert.equal(entries.length,65);
  assert.ok(entries.every((e,i)=>!i||e.command===entries[i-1].command+1));
  const begin=entries[0],restored=entries.find(e=>e.ip===0x8F);
  assert.ok(restored);
  assert.deepEqual(raw.map(k=>begin.state.ik1302.r[k]),payload);
  assert.deepEqual(raw.map(k=>restored.state.ik1302.r[k]),payload);
  assert.equal(begin.state.ik1302.s1,1);
  assert.equal(begin.state.ik1302.st[25],0);
  assert.equal(begin.state.ik1302.r[41],0);
  const beginIndex=t.events.findIndex(e=>e.ip===0x8C);
  const endIndex=t.events.findIndex((e,i)=>i>beginIndex&&e.ip===0x85);
  assert.ok(beginIndex>=0&&endIndex>beginIndex);
  assert.ok(!t.events.slice(beginIndex,endIndex).some(e=>[0x75,0xD4].includes(e.ip)));
  assert.deepEqual(listing(c),program);assert.deepEqual(fullMsPages(c),ms);
  if(mirror) {
    const plain=prepareReader(spec);finish(plain.c,phase);
    assert.deepEqual(machineSnapshot(plain.c),machineSnapshot(c));
  }
  const report={phaseOffset:phase,entryCommand:begin.command,
    entryPhase:begin.state.ir2a.tick,entrySlot:begin.slot,
    ST25:0,R41:0,raw6HeldAt8F:true,programHeld:true,MsHeld:true,
    observerIndependent:mirror,nativeWriter:false};
  if(log)console.log(JSON.stringify(report));
  return {report,entries,mapping:layout()};
}
if(require.main===module) {
  if(process.argv.includes('--proof-input'))
    console.log(JSON.stringify([0,1,2].map(p=>capture(p,{mirror:false,log:false}))));
  else {
    for(const phase of [0,1,2])capture(phase);
    console.log('PASS three genuine frame-phase controls and fresh ALL5 mirrors; '
      +'native signs remain0, no keyboard writer or partialK2.');
  }
}
module.exports={capture,finish};
