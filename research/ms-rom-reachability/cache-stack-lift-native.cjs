#!/usr/bin/env node
'use strict';
// Source-directed negative controls for the digit/stack-lift alternative.
// No state injection or ROM edits. Inputs/timing are fixed; observers passive.
const assert=require('node:assert/strict');
const {prepare}=require('./cache-d8-native.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const raw=[0,3,9,12,18,21];
const lane=a=>a.filter((_,j)=>j<36&&j%3===0);
const hex=code=>code.toString(16).toUpperCase();
const stopFixture={name:'raw_hex_next_stop',
  bytes:[1,2,3,0xA3,0xD4,0xB5,0x50],
  keys:['1','2','3','K','ПП','3','K','П→X','4','K','X→П','5','С/П']};

function digitCheck(f=fixtures[1],digit=1,options={}, {mirror=true,log=true}={}) {
  assert.ok(Number.isInteger(digit)&&digit>=0&&digit<=9);
  const calc=prepare(f,options),initial=machineSnapshot(calc);
  const payload=raw.map(j=>calc.ik1302.r[j]);
  const ms=fullMsPages(calc);
  const program=Array.from({length:105},(_,j)=>calc.readCommand(j));
  const keys=['F','Сx',String(digit)];
  assert.equal(initial.ik1302.r[41],0,'reader leaves stack lift disabled');
  const completePrefix=[];
  let collecting=false,afterFirstWriter=false,collected=false;
  const result=trace(calc,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,j)=>j),fullState:true,allWrites:true,
    otherChipsAt:e=>{
      if(e.ip===0x8D&&!collecting&&!collected)collecting=true;
      if(collecting) {
        completePrefix.push({ip:e.ip,command:e.command,state:machineSnapshot(calc)});
        if(afterFirstWriter){collecting=false;collected=true;}
        if(e.ip===0xE7)afterFirstWriter=true;
      }
      return false;
    },
  });
  const inlet=result.events.find(e=>e.ip===0x8D);
  const gate=result.events.find(e=>e.ip===0x85);
  assert.ok(inlet&&gate);
  assert.equal(inlet.s1,digit);
  assert.equal(inlet.r[41],0);
  assert.deepEqual(raw.map(j=>inlet.r[j]),payload);
  assert.equal(gate.s,0,'84 copies the disabled R41 flag into S');
  assert.equal(gate.r[26],1);
  assert.equal(gate.nextIp,0x88,'85 selects88, not the raw-preserving lift87');
  assert.deepEqual(raw.map(j=>gate.r[j]),payload);
  assert.ok(!result.events.some(e=>[0x87,0xA7,0xA8,0xEE].includes(e.ip)));
  const writer=result.events.filter(e=>e.ip===0xE7);
  assert.equal(writer.length,1);
  assert.equal(writer[0].slot,'X');
  const entered=Array(12).fill(0);entered[7]=digit;
  assert.deepEqual(lane(writer[0].r),entered,
    'writer gets only the entered digit, not the original program cache');
  const writes=result.writes.filter(e=>e.chip===3);
  assert.equal(writes.length,12);
  assert.ok(writes.every(e=>e.ip===0xE7&&e.slot==='X'));
  assert.deepEqual(fullMsPages(calc),ms);
  assert.deepEqual(Array.from({length:105},(_,j)=>calc.readCommand(j)),program);
  if(mirror) {
    const plain=prepare(f,options);plain.pressSequence(keys);aligned(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc),
      'fresh complete five-chip mirror, fixed inputs and no observers');
  }
  const start=result.events.indexOf(inlet),end=result.events.indexOf(writer[0]);
  const prefix=result.events.slice(start,end+1);
  assert.ok(prefix.every((e,j)=>!j||e.command===prefix[j-1].command+1));
  const report={fixture:f.name,digit,options,keys,cacheHeldAt85:true,
    nativeR41:0,branch:'85→88',noEE:true,noStackLift:true,
    writerSlot:'X',writerHasOnlyEnteredDigit:true,
    all56MsBytesHeld:true,programHeld:true,observerIndependent:mirror,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  assert.equal(completePrefix.length,prefix.length+1);
  return {report,initial:initial.ik1302,inlet,prefix,completePrefix};
}

function flagCheck({mirror=true,log=true}={}) {
  // STOP at the next program address is an ordinary keyboard fixture, not
  // a change to the emulator ROM or a fabricated internal return address.
  const calc=prepare(stopFixture,{}),initial=machineSnapshot(calc);
  const keys=['F','Сx','С/П'],payload=raw.map(j=>calc.ik1302.r[j]);
  const action=c=>{c.pressSequence(keys);c.runFrames(12);aligned(c);};
  const result=trace(calc,action,{
    extraIps:Array.from({length:256},(_,j)=>j),fullState:true,allWrites:true,
  });
  const setter=result.events.find(e=>e.ip===0x9F),ee=result.events.find(e=>e.ip===0xEE);
  assert.ok(setter&&ee&&setter.command<ee.command);
  assert.equal(setter.r[33],5);
  const index=result.events.indexOf(setter);
  const setterRoute=[];
  for(const e of result.events.slice(index,result.events.indexOf(ee)+1)) {
    // Collapse ONLY the separately proved field-preserving E5 wait.
    if(e.ip!==0xE5||setterRoute.at(-1)!==0xE5)setterRoute.push(e.ip);
  }
  assert.deepEqual(setterRoute,
    [0x9F,0xAA,0xE5,0xE6,0xED,0xEE]);
  assert.equal(result.events[index+1].r[41],15);
  assert.deepEqual(raw.map(j=>ee.r[j]),payload);
  assert.deepEqual(result.writes.filter(e=>e.chip===3&&e.command<ee.command),[]);
  const after=result.events[result.events.indexOf(ee)+1];
  assert.deepEqual(lane(after.r),ee.m.filter((_,j)=>j<36&&j%3===1));
  assert.notDeepEqual(raw.map(j=>after.r[j]),payload);
  if(mirror) {
    const plain=prepare(stopFixture,{});action(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc));
  }
  const report={fixture:stopFixture.name,keys,nativeSetter:'9F',
    R41AfterSetter:15,nextRead:'EE',noReserveBeforeEE:true,
    cacheReplacedByEE:true,observerIndependent:mirror,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,initial:initial.ik1302,setter,ee};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input')) {
    console.log(JSON.stringify(digitCheck(fixtures[1],1,{}, {mirror:false,log:false})));
  } else {
    for(const f of fixtures)for(const digit of [0,1,9])digitCheck(f,digit);
    digitCheck(fixtures[1],1,{phaseOffset:1});
    digitCheck(fixtures[1],9,{phaseOffset:2,settleFrames:10});
    flagCheck();
    console.log('PASS: eight native digit controls, one native flag setter, '+
      'nine fresh full-five-chip mirrors. No native program-cache export.');
  }
}
module.exports={digitCheck,flagCheck,raw,stopFixture};
