#!/usr/bin/env node
'use strict';
// Two ROM-directed keyboard protocols, not an exhaustive key search.
// Native source/negative controls only: NO D/E/F substitution or setters.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fixtures,install}=require('./check_partial_k2_program_scan.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {prepareSelector}=require('./st34-origin-trace.cjs');
const {finishSignature700}=require('./check_ac_signature_keyboard.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const raw=[0,3,9,12,18,21],bridge=['F','Сx',','];

function prepare({pointer='9'}={}) {
  const calc=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw Error('Forbidden state setter: '+name);};
  install(calc,fixtures[1]);preparePayload('8.7654321E-91',calc);
  // Ordinary P8=9 by default is the pointer for the indirect controls. It is
  // installed through keys BEFORE arithmetic preparation, not a host write.
  calc.inputNumber(String(pointer),{clear:true}).pressSequence(['X→П','8']);
  const ms=fullMsPages(aligned(calc));
  prepareSelector(calc,{selector:9});finishSignature700(calc);aligned(calc);
  assert.deepEqual(fullMsPages(calc),ms,'setup holds all56 seeded Ms bytes');
  return calc;
}

function finish(calc,recall) {
  calc.pressSequence(recall).runFrames(8);aligned(calc);
  calc.pressSequence(bridge);aligned(calc);
}

function capture(indirect,{mirror=true,log=true}={}) {
  const calc=prepare(),recall=indirect?['K','П→X','8']:['П→X','9'];
  const ms=fullMsPages(calc),program=Array.from({length:105},(_,i)=>calc.readCommand(i));
  const result=trace(calc,c=>finish(c,recall),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
  });
  const events=result.events,c8=events.findIndex(e=>e.ip===0xC8);
  assert.ok(c8>=0,'each fixed recall really reaches the program reader');
  const ac=events.findLastIndex((e,i)=>i<c8&&e.ip===0xAC);
  const ab=events.findLastIndex((e,i)=>i<ac&&e.ip===0xAB);
  assert.ok(ab>=0&&ac>ab);
  assert.equal(events[ab].r[35],6,'resolved recall uses the AD/type6 branch');
  assert.equal(events[ab+1].ip,0xAD);
  assert.equal(events[ab+1].r[26],15,'AB really creates native F');
  assert.equal(events[ab+2].ip,0xA6);
  assert.equal(events[ab+2].r[26],0,'AD clears it before the data reader');
  assert.ok(events.slice(ab+2,ac+1).every(e=>e.r[26]===0));
  assert.equal(events[ac-1].ip,0xA9,'native AC comes from the lift return, not direct AA');
  assert.equal(events[ac].r[26],0);
  assert.equal(events[ac].r[31]+16*events[ac].r[34],0x58);
  assert.equal(events[ac].r[1],5);
  assert.equal(events[ac].st[32],15);
  assert.equal(events[ac].st[35],9);
  assert.equal(events[c8].st[24],0);
  const inlet=events.findIndex((e,i)=>i>c8&&e.ip===0x8C);
  const dc=events.findIndex((e,i)=>i>inlet&&e.ip===0xDC);
  assert.ok(inlet>c8&&dc>inlet);
  assert.equal(events[inlet].st[24],0);
  assert.equal(events[dc].r[25],0,'the native DC.B8 gate is STILL closed');
  assert.equal(events[dc].r[34],15,'native header is F, NOT4');
  const payload=fixtures[1].bytes.slice(3,6).flatMap(v=>[v&15,v>>4]);
  assert.deepEqual(raw.map(k=>events[inlet].r[k]),payload);
  assert.deepEqual(raw.map(k=>events[dc].r[k]),payload);
  // Indirect resolution can already execute D4 BEFORE the program reader.
  // Do not confuse that ordinary write with exporting the later raw cache.
  const priorD4=events.filter((e,i)=>i<c8&&e.ip===0xD4).map(e=>({
    command:e.command,slot:e.slot,header:e.r[34],B8:e.r[25],R26:e.r[26],
    ST24:e.st[24],raw6:raw.map(k=>e.r[k]),
  }));
  assert.ok(!events.slice(c8).some(e=>e.ip===0xD4),'no D4 after the cache reader');
  for(const e of priorD4)assert.notDeepEqual(e.raw6,payload,
    'the fixture cache is NOT the data of the earlier D4');
  assert.deepEqual(fullMsPages(calc),ms);
  assert.deepEqual(Array.from({length:105},(_,i)=>calc.readCommand(i)),program);
  const acToC8=events.slice(ac,c8+1);
  assert.ok(acToC8.every((e,i)=>!i||e.command===acToC8[i-1].command+1));
  if(mirror) {
    const plain=prepare();finish(plain,recall);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc),
      'fresh unobserved identical fixed keys reproduce ALL5 chip states/ports');
  }
  const report={recall,bridge,indirect,programReaderReached:true,
    nativeABCreatesF:true,nativeADClearsF:true,nativeACFromA9:true,
    AC_R26:0,C8_ST24:0,inlet8C_ST24:0,DC_B8:0,DC_header:15,
    raw3HeldAtDC:true,all56MsBytesHeld:true,all105ProgramBytesHeld:true,
    observerIndependent:mirror,nativeD4BeforeReader:priorD4,
    nativeCacheD4:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,acToC8};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))
    console.log(JSON.stringify([false,true].map(indirect=>capture(indirect,{mirror:false,log:false}))));
  else {
    for(const indirect of [false,true])capture(indirect);
    console.log('PASS two source-driven direct/indirect recalls and two fresh ALL5-chip mirrors; '+
      'AB F is reset by AD, ST24/B8 stay zero; no native cache-export D4 entry.');
  }
}
module.exports={prepare,finish,capture};
