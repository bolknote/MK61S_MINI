#!/usr/bin/env node
'use strict';
// Two fixed reader→indirect-call controls, NOT all routes or key schedules.
// The standalone DA witness works; merely concatenating these keys does NOT
// preserve the cache or produce the same call00 input. No native setters.
const assert=require('node:assert/strict');
const {prepare}=require('./cache-da-keyboard.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {prepareSelector}=require('./st34-origin-trace.cjs');
const {finishSignature700}=require('./check_ac_signature_keyboard.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const raw=[0,3,9,12,18,21];
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const suffix=['БП','0','0','K','ПП','8'];

function prepareReader(fixture) {
  const c=prepare({fixture}),ms=fullMsPages(c);
  prepareSelector(c,{selector:9});finishSignature700(c);aligned(c);
  assert.deepEqual(fullMsPages(c),ms);
  const program=listing(c);
  const witness=trace(c,c=>{c.pressSequence(['П→X','9']).runFrames(8);aligned(c);},
    {extraIps:[0xC8],fullState:true});
  assert.deepEqual(witness.primitives,[0xC8]);
  assert.deepEqual(listing(c),program);
  assert.deepEqual(fullMsPages(c),ms);
  const payload=fixture.bytes.slice(3,6).flatMap(v=>[v&15,v>>4]);
  assert.deepEqual(raw.map(k=>c.ik1302.r[k]),payload);
  return {c,payload,program,ms};
}

function finish(c) {c.pressSequence(suffix);aligned(c);}

function capture(fixture,{mirror=true,log=true}={}) {
  const {c,payload,program,ms}=prepareReader(fixture);
  const t=trace(c,finish,{extraIps:Array.from({length:256},(_,i)=>i),fullState:true});
  const at=t.events.findIndex(e=>e.ip===0x73);assert.ok(at>=0);
  const call=t.events[at],load=t.events.findLast((e,i)=>i<at&&e.ip===0xD6);
  assert.ok(load);
  const eeAt=t.events.findIndex(e=>e.ip===0xEE);
  const firstD6=t.events.findIndex(e=>e.ip===0xD6);
  assert.ok(eeAt>=0&&firstD6>eeAt,'ordinary-X read precedes indirect pointer load');
  assert.deepEqual(raw.map(k=>t.events[eeAt].r[k]),payload);
  assert.notDeepEqual(raw.map(k=>t.events[eeAt+1].r[k]),payload,
    'the naive suffix first replaces the program cache at EE, not only at laterD6');
  assert.equal(call.r[33],15,'the native pointer still suppliesF');
  assert.notEqual(call.pc,0,'this raw-reader scanner did NOT establish PC00');
  assert.equal(t.events[at+1].ip,0x6F,'not the standalone call75 branch');
  assert.deepEqual(raw.map(k=>call.r[k]),[15,15,15,15,0,9]);
  assert.deepEqual(t.events.filter(e=>e.ip===0xDA),[]);
  assert.deepEqual(t.primitives,[],'no second C8 in this fixed suffix');
  assert.deepEqual(listing(c),program,'ALL105 program bytes held');
  assert.deepEqual(fullMsPages(c),ms,'ALL56 Ms bytes held');
  assert.equal(c.ik1302.r[36]+16*c.ik1302.r[39],0x35);
  const state=machineSnapshot(c);
  if(mirror) {
    const plain=prepareReader(fixture);finish(plain.c);
    assert.deepEqual(machineSnapshot(plain.c),state,'fresh unobserved ALL5-chip reader/suffix mirror');
    assert.deepEqual(listing(plain.c),program);
    assert.deepEqual(fullMsPages(plain.c),ms);
  }
  const report={fixture:fixture.name,suffix,readRaw6:payload,
    at73Raw6:raw.map(k=>call.r[k]),at73PC:call.pc,at73Next:0x6F,
    atD6PointerWord:load.m.filter((_,i)=>i%3===0).slice(0,12),
    firstEECommand:t.events[eeAt].command,firstD6Command:t.events[firstD6].command,
    cacheHeldUntilFirstEE:true,cacheChangedAtFirstEE:true,
    nativeDA:false,all105ProgramBytesHeld:true,all56MsBytesHeld:true,
    observerIndependent:mirror,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,state};
}

function compareWorkingStates(left,right) {
  const changed=[];
  for(const [name,a] of Object.entries(left.state)) {
    const b=right.state[name];
    for(const [field,value] of Object.entries(a)) {
      if(Array.isArray(value))value.forEach((v,k)=>{
        if(v!==b[field][k])changed.push([name,field,k]);
      });
      else if(value!==b[field])changed.push([name,field]);
    }
  }
  assert.deepEqual(changed,[14,17,20,23,26,29].map(k=>['ik1302','m',k]),
    'these two final ALL5-chip states differ ONLY in the six original programme tetras');
  console.log('PASS two concrete reader payloads: final working states/ring/ports differ '+
    'ONLY in original programme bytes87..89; not a universal cache-loss theorem.');
}

if(require.main===module) {
  const cases=fixtures.map(f=>capture(f));compareWorkingStates(...cases);
  console.log('LIMIT: fixed naive concatenation fails; standalone nativeDA remains valid. '+
    'Need compatible reader→writer transport and PC00, not merely sourceF.');
}
module.exports={prepareReader,finish,capture,compareWorkingStates};
