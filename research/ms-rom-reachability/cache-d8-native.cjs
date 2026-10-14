#!/usr/bin/env node
'use strict';
// Negative native continuation witness, never a partial-K2 success. Fixed
// keys/waits only; passive snapshots; a fresh unobserved complete mirror.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {prepareSelector,finishSelector}=require('./st34-origin-trace.cjs');
const {fixtures,install}=require('./check_partial_k2_program_scan.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const raw=[0,3,9,12,18,21], lane=(a,n)=>a.slice(n,36).filter((_,j)=>j%3===0);
const keys=['F','Сx',','];
const bMetadata=[0,8,8,8,8,8,8,0,0,0,9,15];
const cMetadata=[8,0,0,0,0,0,0,0,0,0,8,15];
const prefix=[0xDC,0xEA,0xD8,0xF2,
  ...Array.from({length:8},()=>[0xF3,0xF7,0xF1]).flat(),
  0xF4,0xF6,0xF4,0xEA,0xEC,0x40];

function prepare(f,options) {
  const calc=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw Error('Forbidden state setter: '+name);};
  install(calc,f);preparePayload('8.7654321E-91',calc);
  const settings={...options,selector:9};
  prepareSelector(calc,settings);finishSelector(calc,settings);aligned(calc);
  assert.deepEqual(raw.map(j=>calc.ik1302.r[j]),
    f.bytes.slice(3,6).flatMap(v=>[v&15,v>>4]));
  return calc;
}

function check(f,options={}) {
  const calc=prepare(f,options),ms=fullMsPages(calc);
  const program=Array.from({length:105},(_,j)=>calc.readCommand(j));
  const payload=raw.map(j=>calc.ik1302.r[j]);
  const result=trace(calc,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,j)=>j),fullState:true,allWrites:true,
  });
  const start=result.events.findIndex(e=>e.ip===0xDC);
  assert.ok(start>=0);
  const events=result.events.slice(start,start+prefix.length);
  assert.deepEqual(events.map(e=>e.ip),prefix);
  assert.deepEqual(raw.map(j=>events[0].r[j]),payload);
  assert.deepEqual(lane(events[0].r,0).slice(9),[10,9,9]);
  assert.deepEqual(lane(events[0].r,1),bMetadata);
  assert.deepEqual(lane(events[0].r,2),cMetadata);
  for(let j=1;j<events.length;j++)
    assert.equal(events[j].command,events[j-1].command+1);
  const at40=events.at(-1);
  assert.deepEqual(lane(at40.r,0),Array(12).fill(0));
  assert.deepEqual(result.writes.filter(w=>w.chip===3&&w.command<at40.command),[]);
  assert.ok(!result.events.some(e=>e.ip===0xEE),'this scrub does not use EE');
  const writers=result.events.filter(e=>e.ip===0xE7);
  assert.equal(writers.length,1);
  assert.equal(writers[0].slot,'X','the selected natural writer writes X, not Ms');
  assert.deepEqual(lane(writers[0].r,0),Array(12).fill(0));
  assert.deepEqual(fullMsPages(calc),ms,'all56 Ms bytes held, not written');
  assert.deepEqual(Array.from({length:105},(_,j)=>calc.readCommand(j)),program);
  const plain=prepare(f,options);plain.pressSequence(keys);aligned(plain);
  assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc),
    'fixed identical inputs reproduce all5 chips without observers');
  const report={fixture:f.name,options,rawBytes:f.bytes.slice(3,6),
    nativeD8Scrub:true,all12AZeroBefore40:true,noEE:true,
    noPrimaryWriteBefore40:true,naturalWriterSlot:'X',naturalWriterValueZero:true,
    all56MsBytesHeld:true,programHeld:true,observerIndependent:true,partialK2:false};
  console.log(JSON.stringify(report));
  return {report,events};
}

if(require.main===module) {
  for(const [f,options] of [[fixtures[0],{}],[fixtures[1],{}],
    [fixtures[1],{phaseOffset:1}],
    [fixtures[1],{phaseOffset:2,settleFrames:10}]])check(f,options);
  console.log('PASS: four fixed native D8 scrubs, four fresh full5-chip mirrors; '+
    'the natural writer writes zero to X, not the program cache to Ms.');
}
module.exports={check,prepare,prefix,bMetadata,cMetadata};
