#!/usr/bin/env node
'use strict';
// Investigate the program-to-Ms half, not a successful partial K2.
// All fixtures and operations use ordinary keys. Observers never control
// execution or feed the captured program byte back to the calculator.
const assert=require('node:assert/strict');
const {run,preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {prepareCombined,finishCombined}=require('./check_ac_signature_keyboard.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const lane=(a,n)=>a.filter((_,i)=>i%3===n);
const hex=a=>a.map(n=>n.toString(16).toUpperCase()).join('');
const value='8.7654321E-71';
const fixtures=[
  {name:'digits',bytes:[1,2,3,4,5,6,7],keys:['1','2','3','4','5','6','7']},
  {name:'other_six',bytes:[0x22,0x10,0x24,0x12,0x50,6,0x14],
    keys:['F','*','+','F','↔','*','С/П','6','↔']},
  {name:'target_x2',bytes:[1,2,3,4,5,0x22,7],
    keys:['1','2','3','4','5','F','*','7']},
  {name:'target_indirect',bytes:[1,2,3,4,5,0xA5,7],
    keys:['1','2','3','4','5','K','ПП','5','7']},
];

function forbidSetters(calc) {
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw Error('Forbidden host setter: '+name);};
}

function installFixture(calc,fixture) {
  calc.pressSequence(['БП','8','4','F','ВП',...fixture.keys,'F','/-/','В/О']);
  assert.deepEqual(Array.from({length:7},(_,i)=>calc.readCommand(84+i)),fixture.bytes);
}

function plain(fixture,options) {
  const calc=new MK61();forbidSetters(calc);
  installFixture(calc,fixture);
  preparePayload(value,calc);
  prepareCombined({calc,counter:1});
  calc.runFrames(options.phaseOffset||0);
  finishCombined(calc,options);
  return aligned(calc);
}

function capture(fixture=fixtures[0],options={}) {
  const result=run(value,{...options,prepareProgram:c=>installFixture(c,fixture)});
  const events=result.tail,swaps=events.filter(e=>e.ip===0xC9);
  assert.equal(events.filter(e=>e.ip===0xC8).length,1);
  assert.equal(swaps.length,2);
  const first=swaps[0],second=swaps[1];
  assert.equal(first.slot,'Y');assert.equal(second.slot,first.slot);
  assert.equal(second.command-first.command,60);
  const after=events.find(e=>e.command===second.command+1);
  assert.equal(after.ip,0x06);
  const byte=after.r[30]+16*after.r[33];
  assert.equal(byte,fixture.bytes[5],'the selected byte is address 89, not a whole page');
  assert.deepEqual(lane(second.r,1),lane(first.m,2),'the old program is put back');
  assert.deepEqual(lane(after.r,1),lane(first.r,1),'the parked scratch word is recovered');
  assert.deepEqual(result.report.fullAfter,result.report.fullBefore,'all 56 Ms bytes held');
  assert.deepEqual(result.report.programChanges,[{address:70,before:0,after:0x0E}],
    'only the pre-C8 ENTER from the established witness changes the listing');
  assert.deepEqual(Array.from({length:7},(_,i)=>result.calc.readCommand(84+i)),fixture.bytes);
  const stopped=machineSnapshot(result.calc),beforeIdle=digest(result.calc);
  result.calc.runFrames(60);
  assert.equal(digest(result.calc),beforeIdle,'the final cache is stable at this fixed boundary');
  const withoutObserver=plain(fixture,options);
  assert.deepEqual(machineSnapshot(withoutObserver),stopped,
    'the complete fresh unobserved calculator must agree, including the ring');
  assert.deepEqual(fullMsPages(withoutObserver),result.report.fullBefore);
  return {result,first,second,after,stopped,fixture,options,
    report:{name:fixture.name,options,selectedAddress:89,selectedByte:byte,
      sourceSlot:result.first.slot,programSlot:first.slot,
      oldProgram:hex(lane(first.m,2)),afterPairA:hex(lane(after.r,0).slice(0,12)),
      finalA:hex(lane(stopped.ik1302.r,0).slice(0,12)),allMsHeld:true,
      programReturned:true,observerIndependent:true}};
}

function proofInput() {
  const c=capture();
  const start=c.result.tail.indexOf(c.first),end=c.result.tail.indexOf(c.second);
  const events=c.result.tail.slice(start,end+2);
  assert.equal(events.length,62);
  for(let i=1;i<events.length;i++)
    assert.equal(events[i].command,events[i-1].command+1,'unabridged command stream');
  return {scope:'local program-byte read on one observed native continuation; NOT K2',
    first:events[0],events,selectedAddress:89,selectedPacketTetras:[8,9]};
}

function check() {
  const cases=fixtures.map(f=>capture(f));
  const base=cases[0];
  for(const c of cases)console.log(JSON.stringify(c.report));
  for(const name of ['r','st','s','s1','l','t','carry'])
    assert.deepEqual(cases[1].stopped.ik1302[name],base.stopped.ik1302[name],
      'changing all six unselected bytes leaves the IK1302 cache unchanged');
  for(const c of cases.slice(2)) {
    const difference=base.stopped.ik1302.r.flatMap((n,i)=>n===c.stopped.ik1302.r[i]?[]:[i]);
    assert.deepEqual(difference,[18,21],'only the selected low/high byte cache differs');
    assert.equal(c.stopped.ik1302.r[18]+16*c.stopped.ik1302.r[21],c.fixture.bytes[5]);
    for(const name of ['st','s','s1','l','t','carry'])
      assert.deepEqual(c.stopped.ik1302[name],base.stopped.ik1302[name]);
  }
  for(const options of [{phaseOffset:1},{phaseOffset:2,settleFrames:10}]) {
    const c=capture(fixtures[3],options);
    console.log(JSON.stringify(c.report));
  }
  console.log('PASS: six keyboard fixtures, six fresh complete-state mirrors. '+
    'One raw program byte survives in A; no program-to-Ms write or partial K2.');
  return cases;
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(proofInput()));
  else check();
}
module.exports={fixtures,capture,proofInput,check};
