#!/usr/bin/env node
'use strict';
// Fixed, ROM-directed keyboard continuations. Passive observation only.
// Reaching DC with intact raw bytes is not a persistent program-to-Ms write.
const assert=require('node:assert/strict');
const {reader,plainReader}=require('./check_partial_k2_cache_exit.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const positions=[0,3,9,12,18,21];
const route=[0x8C,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,
  0x93,0x94,0x95,0x98,0x9A,0x8D,0x4F,0xAF,0xAE,0xDC];
const lanes=[0,0,1,2,2,2,2,2,1,1,1,1,0,0,0,0,0,0];
const hex=a=>a.map(n=>n.toString(16).toUpperCase()).join('');
// AF's numeric test can alter the writer header, even though the raw bytes
// themselves are held. This fixture comes from that exact dataflow predicate.
const adjustedFixture={name:'zero_zero_e0',bytes:[1,2,3,0,0,0xE0,7],
  keys:['1','2','3','0','0','K','ШГ←','0','7']};

function capture(f=fixtures[1],options={},keys=['F','Сx',','],
    {mirror=true,expectedDcHeader=15}={}) {
  const calc=reader(f,options),initial=machineSnapshot(calc);
  const payload=positions.map(n=>calc.ik1302.r[n]);
  const ms=fullMsPages(calc),program=Array.from({length:105},(_,i)=>calc.readCommand(i));
  const result=trace(calc,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
  });
  const start=result.events.findIndex(e=>e.ip===0x8C);
  let bridge=[];
  if(keys.length===2) {
    assert.equal(start,-1,'F Сx alone does not run the bridge');
    assert.equal(calc.ik1302.r[23],0,'F prefix B3 clears opcode construction flag');
    assert.deepEqual(positions.map(n=>calc.ik1302.r[n]),payload);
    assert.equal(calc.ik1302.stack[34],15);
    assert.ok(!result.events.some(e=>e.ip===0xEE));
    assert.deepEqual(result.writes.filter(w=>w.chip===3),[]);
  } else {
    assert.ok(start>=0,'fixed F Сx comma reaches 8C');
    bridge=result.events.slice(start,start+route.length);
    assert.deepEqual(bridge.map(e=>e.ip),route,'one natural double restore followed by DC');
    for(let i=0;i<bridge.length;i++) {
      if(i)assert.equal(bridge[i].command,bridge[i-1].command+1);
      assert.deepEqual(positions.map(n=>bridge[i].r[n+lanes[i]]),payload,
        `all three raw bytes in lane ${lanes[i]} before ${route[i].toString(16)}`);
    }
    const dc=bridge.at(-1),before=result.events.filter(e=>e.command<=dc.command);
    assert.ok(!before.some(e=>e.ip===0xEE),'no numeric reread before DC');
    assert.deepEqual(result.writes.filter(w=>w.chip===3&&w.command<dc.command),[],
      'no primary ring writer before DC');
    assert.equal(dc.r[34],expectedDcHeader,'AF-adjusted writer selector');
    assert.equal(result.events[start+route.length].ip,expectedDcHeader===1?0xDE:0xEA);
    assert.ok(!result.events.some(e=>[0xD4,0xBC].includes(e.ip)),
      'selected native continuation has no cache writer');
    if(expectedDcHeader===1) {
      assert.ok(result.events.some(e=>e.ip===0xD1),'header one dispatches D1, not D4');
      assert.ok(result.events.some(e=>e.ip===0xD2),'paired restore returns to D2');
      assert.deepEqual(result.writes.filter(w=>w.chip===3),[],
        'header-one selected continuation has no primary ring write');
    } else assert.ok(!result.events.some(e=>e.ip===0xDE));
  }
  assert.deepEqual(fullMsPages(calc),ms,'all 56 Ms bytes held after the continuation');
  assert.deepEqual(Array.from({length:105},(_,i)=>calc.readCommand(i)),program,
    'complete visible program held after the reader continuation');
  if(mirror) {
    const plain=plainReader(f,options);plain.pressSequence(keys);aligned(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc),
      'fresh complete unobserved mirror uses the same fixed keys and waits');
  }
  return {initial:initial.ik1302,events:bridge,report:{fixture:f.name,options,keys,
    payload:f.bytes.slice(3,6),bridge:bridge.map((e,i)=>({
      ip:e.ip.toString(16).toUpperCase(),lane:'ABC'[lanes[i]]})),
    DCHeader:bridge.length?expectedDcHeader:null,
    all56MsBytesHeld:true,programHeld:true,observerIndependent:mirror,partialK2:false}};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(capture(
    fixtures[1],{},['F','Сx',','],{mirror:false})));
  else {
    for(const [f,options,keys] of [
      [fixtures[1],{},['F','Сx']],
      [fixtures[0],{},['F','Сx',',']],
      [fixtures[1],{},['F','Сx',',']],
      [fixtures[1],{phaseOffset:1},['F','Сx',',']],
      [fixtures[1],{phaseOffset:2,settleFrames:10},['F','Сx',',']],
    ])console.log(JSON.stringify(capture(f,options,keys).report));
    console.log(JSON.stringify(capture(adjustedFixture,{},['F','Сx',','],
      {expectedDcHeader:1}).report));
    console.log('PASS: six native cancellation/bridge cases and six fresh full mirrors; '+
      'three raw bytes survive up to DC; payload-dependent header one enters DE/D1, '+
      'but no partial K2 write.');
  }
}
module.exports={capture,positions,route,lanes,adjustedFixture};
