#!/usr/bin/env node
'use strict';
// Native seven-input source only. Reference state changes solely by public
// keys/frames; no early-counter hypothesis or numeric/controller injection.
const assert=require('node:assert/strict');
const input=require('./cache-control-f-transfer-native.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const word=(values,lane=0)=>Array.from({length:12},(_,i)=>
  values[3*i+lane].toString(16).toUpperCase()).join('');
const data=c=>({program:Array.from({length:105},(_,i)=>c.readCommand(i)),
  ms:fullMsPages(c),registers:Array.from({length:15},(_,i)=>rawMemoryRegister(c,i))});
function prepare() {
  const c=input.prepare();
  c.press('7').runFrames(2);aligned(c);
  return c;
}
function capture({mirror=true,log=true}={}) {
  const c=input.prepare(),before=data(c);
  c.press('7').runFrames(2);aligned(c);
  const after=data(c),entry={command:0,state:machineSnapshot(c)},prefix=[];
  const a=entry.state.ik1302;
  assert.deepEqual(after,before,'native seven preserves all105/56/15 ordinary words');
  assert.equal(c.displayText(),'7,');
  assert.equal(word(a.r),'FFFFFFF7FFFF');
  assert.equal(word(a.r,2),'8088888002FF');
  assert.equal(a.r[36]+16*a.r[39],0x35);
  assert.equal(a.r[21],7);assert.equal(a.r[5],0);assert.equal(a.l,0);
  for(let index=2;index<=6;index++)assert.equal(a.r[3*index+2],8);
  trace(c,c=>c.runFrames(3),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:()=>prefix.length<65,
    otherChipsAt:e=>{
      if(prefix.length<65)
        prefix.push({command:e.command,ip:e.ip,state:machineSnapshot(c)});
      return false;
    },
  });
  assert.equal(prefix.length,65);
  assert.ok(prefix.every((e,i)=>e.command===i));
  const end={command:1680,state:machineSnapshot(c)};
  assert.equal(word(end.state.ik1302.r),'FFFFFFF7FFFF');
  const storeEntry={command:0,state:machineSnapshot(c)},storePrefix=[];
  let storeSaw57=false;
  trace(c,c=>{c.press('X→П').runFrames(2);aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:ip=>{if(ip===0x57)storeSaw57=true;return storePrefix.length<65;},
    otherChipsAt:e=>{
      if(storePrefix.length<65)
        storePrefix.push({command:e.command,ip:e.ip,state:machineSnapshot(c)});
      return false;
    },
  });
  const storeEnd={command:3360,state:machineSnapshot(c)};
  const ready=storePrefix.find(e=>e.ip===0x48);
  assert.equal(storePrefix.length,65);
  assert.equal(ready.command,8);
  assert.equal(word(ready.state.ik1302.r),'FFFFFFF7FFFF');
  assert.equal(ready.state.ik1302.l,1);
  for(let index=1;index<=6;index++)assert.equal(ready.state.ik1302.r[3*index+2],8);
  assert.equal(storeSaw57,false,'native prefix prepares flags but does NOT enter57');
  assert.deepEqual(data(c),before,'STORE prefix only preserves program/Ms/15 ordinary words');
  if(mirror) {
    const plain=input.prepare();data(plain);
    plain.press('7').runFrames(2);aligned(plain);data(plain);plain.runFrames(3);
    assert.deepEqual(machineSnapshot(plain),end.state,'fresh unobserved ALL5 seven mirror');
    plain.press('X→П').runFrames(2);aligned(plain);data(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh unobserved ALL5 STORE-prefix mirror');
  }
  const report={native:true,keys:['7'],A:word(a.r),C:word(a.r,2),A7:a.r[21],
    missingC1:a.r[5],missingL:a.l,nativeC2Through6:Array.from({length:5},(_,i)=>a.r[8+3*i]),
    all105Program56Ms15OrdinaryWordsHeld:true,observerIndependent:mirror,
    nativeData57Ready:{keys:['7','X→П'],ip:'48',relativeCommand:ready.command,
      A:word(ready.state.ik1302.r),C1Through6:Array(6).fill(8),L:ready.state.ik1302.l},
    native57Called:storeSaw57,
    ordinaryCSignFCreated:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,entry,prefix,end,storeEntry,storePrefix,storeEnd};
}
if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(capture({log:false})));
  else {capture();console.log('PASS native seven mask, no counter repair, complete fresh mirror.');}
}
module.exports={prepare,capture};
