#!/usr/bin/env node
'use strict';
// Native control for the existing short A8/top93 return. Only keys and
// frames mutate the reference. The real native target is X, NOT marker;
// the extra P8 marker studied elsewhere is never injected here.
const assert=require('node:assert/strict');
const driver=require('./probe_a8_seven_source.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const markerDriver=require('./probe_a8_marker_route.cjs');

function capture({mirror=true,log=true}={}) {
  const c=driver.prepare(),beforeMs=fullMsPages(c);
  let stage='',started=false,startCommand,previousPins;
  const prefix=[],keySchedule=[];
  const t=trace(c,c=>{driver.finish(c,{},s=>{stage=s;});aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    eventFilter:()=>stage==='recall',
    otherChipsAt:e=>{
      const pins=Object.fromEntries(['ik1302','ik1303','ik1306'].map(name=>
        [name,[c[name].keyX,c[name].keyY]]));
      const encoded=JSON.stringify(pins);
      if(encoded!==previousPins) {
        keySchedule.push({command:e.command,pins});previousPins=encoded;
      }
      if(!started&&e.ip===0xE5&&e.s1===14&&e.sp[0]===0xA8&&e.sp[1]===0x93) {
        started=true;startCommand=e.command;
        assert.equal(e.slot,'Z');
      }
      if(started&&prefix.length<129)
        prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
    ringAt:e=>started&&e.command<startCommand+24,
  });
  assert.equal(prefix.length,129);
  assert.ok(prefix.every((e,i)=>e.command===startCommand+i));
  const events=t.events.filter(e=>e.command>=startCommand&&e.command<startCommand+129);
  const index=events.findIndex(e=>e.ip===0xA8&&e.s1===14);
  assert.equal(events[index].slot,'X');
  assert.deepEqual(events.slice(index,index+7).map(e=>e.ip),
    [0xA8,0xA9,0x93,0x94,0x95,0x98,0x9A]);
  assert.equal(events[index+5].st[25],0);
  assert.ok(events.every(e=>e.st[25]===0),'native control does NOT make saved signF');
  const finalEntry={command:t.events.at(-1).command+1,state:machineSnapshot(c)};
  assert.equal(finalEntry.command%560,0,'public frame boundary, not microtimed keys');
  assert.equal(finalEntry.state.ir2a.tick,84);
  const afterMs=fullMsPages(c);
  assert.deepEqual(afterMs,beforeMs);
  assert.equal(rawMemoryRegister(c,12),'000000000000');
  assert.equal(c.displayText(),'0,');
  if(mirror) {
    const plain=driver.prepare();fullMsPages(plain);
    driver.finish(plain);aligned(plain);fullMsPages(plain);rawMemoryRegister(plain,12);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh ALL5 observer mirror');
  }
  const report={nativeTarget:'X',nativeSavedSign:0,ordinaryPCSignFCreated:false,
    all56MsBytesHeld:true,observerIndependent:mirror,extraP8MarkerCreated:false,
    programExport:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,prefix,events,keySchedule,finalEntry};
}

function compensation({mirror=true,log=true}={}) {
  const actions=[['auto',['F','/-/']],['clear',['Сx']],['seed',['П→X','7']],
    ['save',['F','/-/']],['clear-again',['Сx']],['compensate-X',['П→X','4']]];
  const finish=(c,record=()=>{})=>{
    for(const [name,keys] of actions) {
      record(name);c.pressSequence(keys).runFrames(8);
    }
    aligned(c);
  };
  const c=markerDriver.prepare();let stage='',started=false;
  const prefix=[];
  const t=trace(c,c=>finish(c,s=>{stage=s;}),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:()=>stage==='compensate-X',
    otherChipsAt:e=>{
      if(e.ip===0xA8&&(e.s1&1))started=true;
      if(started&&prefix.length<33)
        prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
  });
  assert.equal(prefix.length,33);
  assert.ok(prefix.every((e,i)=>e.command===prefix[0].command+i&&e.ip===0xA8));
  assert.ok(t.events.slice(-560).every(e=>e.ip===0xA8&&(e.s1&1)));
  assert.equal(c.ik1302.r[36]+16*c.ik1302.r[39],0xA8);
  assert.ok(c.ik1302.s1&1);
  if(mirror) {
    const plain=markerDriver.prepare();finish(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'negative-control ALL5 mirror');
  }
  const report={attempt:'RCL4 after second clear, before address E0/extra marker',
    native:true,firstOddSelector:prefix[0].state.ik1302.s1,endIp:0xA8,
    last560CommandsAllOddA8:true,observerIndependent:mirror,
    preservingPreparation:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,prefix};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify({
    ...capture({mirror:false,log:false}),compensation:compensation({mirror:false,log:false})}));
  else {
    capture();console.log('PASS existing native single-A8/return93, 129 consecutive '
      +'ALL5 snapshots and fresh mirror; target X, saved sign0, Ms held.');
    compensation();console.log('PASS early-X compensation negative control: '
      +'odd A8 tail,33 ALL5 snapshots and fresh mirror; not a finite marker maker.');
  }
}
module.exports={capture,compensation};
