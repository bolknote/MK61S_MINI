#!/usr/bin/env node
'use strict';
// One ROM-directed digit-entry control, not a keyboard search. The actual
// calculator sees only keys: no synthetic sign, header or return assignment.
const assert=require('node:assert/strict');
const {prepareReader}=require('./cache-da-sign-native.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {layout}=require('./cache-d4-native-topology.cjs');
const raw=[0,3,9,12,18,21],suffix=['F','Сx','1'];
const specs=fixtures.flatMap(fixture=>['0','-1'].map(carrier=>({
  fixture,selector:10,carrier,
})));
const restored=[0x8C,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,
  0x93,0x94,0x95,0x98,0x9A,0x8D,0x8F];
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
function finish(c) {c.pressSequence(suffix);aligned(c);}

function capture(spec,{mirror=true,log=true}={}) {
  // prepareReader guards setters and seeds ordinary C before the anomaly.
  const {c,program,ms,payload,sourceSign}=prepareReader(spec);
  const completePrefix=[];let collecting=false;
  const t=trace(c,finish,{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    otherChipsAt:e=>{
      if(e.ip===0x8C&&!completePrefix.length)collecting=true;
      if(collecting&&completePrefix.length<65)
        completePrefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
  });
  const es=t.events,at=es.findIndex(e=>e.ip===0x8C);
  const end=es.findIndex((e,i)=>i>at&&e.ip===0x85);
  assert.ok(at>=0&&end>at);
  const prefix=es.slice(at,end+1);
  assert.ok(prefix.every((e,i)=>!i||e.command===prefix[i-1].command+1));
  assert.equal(completePrefix.length,65);
  assert.ok(completePrefix.every((e,i)=>!i||e.command===completePrefix[i-1].command+1));
  assert.equal(completePrefix[0].command,prefix[0].command);
  assert.deepEqual(prefix.map(e=>e.ip),restored.concat(
    sourceSign===0?[0x81,0x82,0x84,0x85]:[0x82,0x84,0x85]));
  assert.equal(prefix[0].s1,1);assert.equal(prefix[0].r[41],0);
  assert.equal(prefix[0].st[25],sourceSign);
  assert.equal(prefix[0].st[33],10);assert.equal(prefix[0].st[35],5);
  const branch=prefix.find(e=>e.ip===0x8F);
  const increment=prefix.find(e=>e.ip===0x84);
  assert.equal(branch.r[26],sourceSign);assert.equal(branch.r[41],0);
  assert.equal(increment.r[26],sourceSign);
  assert.equal(prefix.at(-1).r[26],sourceSign+1);
  for(const point of [branch,increment,prefix.at(-1)])
    assert.deepEqual(raw.map(k=>point.r[k]),payload,'raw6 held at digit gate');
  assert.ok(!prefix.some(e=>[0xEE,0xD6,0x75,0xCA,0xDA,0xDB,0xD4].includes(e.ip)));
  assert.deepEqual(listing(c),program,'ALL105 program bytes held at completion');
  assert.deepEqual(fullMsPages(c),ms,'ALL56 Ms bytes held at completion');
  const final=machineSnapshot(c);
  if(mirror) {
    const plain=prepareReader(spec);finish(plain.c);
    assert.deepEqual(machineSnapshot(plain.c),final,'fresh unobserved ALL5-chip mirror');
    assert.deepEqual(listing(plain.c),program);assert.deepEqual(fullMsPages(plain.c),ms);
  }
  const report={fixture:spec.fixture.name,selector:spec.selector,carrier:spec.carrier,
    suffix,nativeST25:sourceSign,nativeR41:0,nativeST35:5,
    gate84_R26:sourceSign,nextAfter84:0x85,raw6HeldAtDigitGate:true,
    prefixNoEEorD6:true,nativeCall75:false,nativeD4InPrefix:false,
    all105ProgramBytesHeld:true,all56MsBytesHeld:true,
    observerIndependent:mirror,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,prefix,completePrefix,mapping:layout()};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(
    specs.map(spec=>capture(spec,{mirror:false,log:false}))));
  else {
    for(const spec of specs)capture(spec);
    console.log('PASS four fixed keyboard digit-entry controls and four fresh ALL5 mirrors; '+
      'real gate84, raw6 retained there, decimal C sign0/9 selects85, NOT75.');
  }
}
module.exports={specs,capture,finish,restored};
