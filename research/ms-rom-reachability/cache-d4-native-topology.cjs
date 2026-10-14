#!/usr/bin/env node
'use strict';
// Keyboard-only native NEGATIVE control and passive full-state/topology input.
// Hypothetical D4 positions are inferred from circulating tags, not executed.
const assert=require('node:assert/strict');
const path=require('node:path');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {prepare}=require('./cache-d8-native.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const referenceRoot=process.env.MK61_REFERENCE_ROOT||path.resolve(__dirname,'../../..','MK-61');
const {EXTRA}=require(path.join(referenceRoot,'tests/emulator/probe-pustyshka-capacity.cjs'));
const slots=['marker','control','P7','P8','P9','P10','W','Q','Z','T','U','V','Y','X','X1'];
const locations=[[1,41],[1,83],[1,125],[1,167],[1,209],[1,251],
  [2,41],[2,83],[2,125],[2,167],[2,209],[2,251],[3,41],[4,41],[5,41]];

function locate(chip,index) {
  const page=locations.findIndex(([c,e])=>c===chip&&index>=e-41&&index<=e);
  assert.ok(page>=0,'every phase1 memory cell has a physical tag');
  return {slot:slots[page],nibble:index-(locations[page][1]-41)};
}
function layout() {
  const calc=new MK61(),registerPages={};
  for(let r=0;r<15;r++) {
    const [chip,end]=calc.commandAddress(r*7,1);
    const cells=Array.from({length:12},(_,i)=>locate(chip,end-8-3*i));
    assert.deepEqual(cells.map(c=>c.nibble),Array.from({length:12},(_,i)=>33-3*i));
    assert.ok(cells.every(c=>c.slot===cells[0].slot));
    registerPages[cells[0].slot]=r.toString(16).toUpperCase();
  }
  assert.equal(Object.keys(registerPages).length,15);
  const hidden={};
  for(const [name,[chip,end]] of Object.entries(EXTRA)) {
    const cells=Array.from({length:14},(_,i)=>locate(chip,end+6-3*i));
    assert.deepEqual(cells.map(c=>c.nibble),Array.from({length:14},(_,i)=>40-3*i));
    assert.ok(cells.every(c=>c.slot===name&&c.nibble%3===1));
    hidden[name]=cells.map(c=>c.nibble);
  }
  // Structural induction: every tick swaps cells with the SAME nibble tag.
  // This checks all 42 fields, not only the old tracer's header34 check.
  const tags=locations.map((_,j)=>({slot:slots[j],nibbles:Array.from({length:42},(_,i)=>i)}));
  const arrays=[tags.slice(0,6).flatMap(t=>t.nibbles),
    tags.slice(6,12).flatMap(t=>t.nibbles),...tags.slice(12).map(t=>t.nibbles.slice())];
  for(let command=0;command<30;command++) {
    const j=(84+42*command)%252;
    for(let k=0;k<42;k++) {
      const indices=[j+k,j+k,k,k,k];
      const old=arrays.map((a,n)=>a[indices[n]]);
      assert.deepEqual(old,[k,k,k,k,k]);
      [old[4],old[0],old[1],old[2],old[3]].forEach((v,n)=>arrays[n][indices[n]]=v);
    }
  }
  return {registerPages,hidden,proof:'M1 lane0=ordinary registers; Ms lane1; topology preserves field classes'};
}

function capture({mirror=true,log=true}={}) {
  const calc=prepare(fixtures[1],{}),mapping=layout(),prefix=[];
  const beforeMs=fullMsPages(calc),program=Array.from({length:105},(_,i)=>calc.readCommand(i));
  let collecting=false,inlet=null;
  const keys=['F','Сx',','];
  const result=trace(calc,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    otherChipsAt:e=>{
      if(e.ip===0x8C&&!inlet)
        inlet={ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(calc)};
      if(e.ip===0xDC&&!prefix.length)collecting=true;
      if(collecting&&prefix.length<65)
        prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(calc)});
      return false;
    },
  });
  assert.ok(inlet&&inlet.command<prefix[0].command);
  assert.equal(inlet.state.ik1302.s1,10);
  assert.deepEqual([24,25,34].map(k=>inlet.state.ik1302.st[k]),[0,0,15]);
  assert.equal(prefix.length,65);
  assert.equal(prefix[0].ip,0xDC);
  assert.equal(prefix[0].state.ik1302.r[34],15,'native header is F, NOT4');
  assert.equal(prefix[0].state.ik1302.r[25],0,'native B8 is0, NOT the required D/E/F');
  assert.ok(!result.events.some(e=>e.ip===0xD4),'no native D4 execution');
  assert.deepEqual(fullMsPages(calc),beforeMs);
  assert.deepEqual(Array.from({length:105},(_,i)=>calc.readCommand(i)),program);
  assert.ok(prefix.every((e,i)=>!i||e.command===prefix[i-1].command+1));
  if(mirror) {
    const plain=prepare(fixtures[1],{});plain.pressSequence(keys);aligned(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc));
  }
  const hypotheticalDestinations=[2,4].map(offset=>({
    offset,slot:prefix[offset].slot,ordinaryRegister:mapping.registerPages[prefix[offset].slot],
    lane:'M1',nativeD4:false,
  }));
  const report={nativeD4:false,header:15,B8:0,programHeld:true,all56MsBytesHeld:true,
    observerIndependent:mirror,conditionalDestinations:hypotheticalDestinations,
    native8CMetadata:{S1:10,ST24:0,ST25:0,ST34:15},
    partialK2:false};
  if(log)console.log(JSON.stringify({mapping,report}));
  return {mapping,report,prefix,inlet};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))
    console.log(JSON.stringify(capture({mirror:false,log:false})));
  else capture();
}
module.exports={capture,layout,slots,locations};
