#!/usr/bin/env node
'use strict';
// Native digit1 followed by ordinary STORE C. Only public keys/frames act on
// the reference; all snapshots/hooks are passive, and four setters forbidden.
const assert=require('node:assert/strict');
const input=require('./cache-control-f-transfer-native.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const keys=['X→П','ВП']; // C is selected by the EXP key.
const word=a=>Array.from({length:12},(_,i)=>a[3*i].toString(16).toUpperCase()).join('');
const data=c=>({program:Array.from({length:105},(_,i)=>c.readCommand(i)),
  ms:fullMsPages(c),registers:Array.from({length:15},(_,i)=>rawMemoryRegister(c,i))});
function finish(c) {c.pressSequence(keys).runFrames(2);aligned(c);}

function capture({mirror=true,log=true}={}) {
  const c=input.prepare();input.finish(c);
  const entry={command:0,state:machineSnapshot(c)},before=data(c),prefix=[],second=[],writers=[];
  trace(c,finish,{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:()=>second.length<90,
    otherChipsAt:e=>{
      if(prefix.length<65)
        prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      if(e.command>=1120&&second.length<90)
        second.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
    onWrite:e=>{
      if(e.chip===3&&e.ip===0xD4&&e.nibble===24)
        writers.push({command:e.command,slot:e.slot,sign:e.value});
    },
  });
  const end={command:3360,state:machineSnapshot(c)},after=data(c);
  assert.equal(prefix.length,65);
  assert.equal(second.length,90);
  assert.equal(second[0].command,1120);
  assert.ok(second.some(e=>e.ip===0xD4&&e.slot==='Y'));
  assert.deepEqual(after.program,before.program);
  assert.deepEqual(after.ms,before.ms);
  assert.equal(before.registers[12],'000000000000');
  assert.equal(after.registers[12],'000010000000');
  for(let i=0;i<15;i++)if(i!==12)assert.equal(after.registers[i],before.registers[i]);
  assert.ok(writers.some(e=>e.slot==='Y'&&e.sign===0),'native numeric writer C/sign0');
  if(mirror) {
    const plain=input.prepare();input.finish(plain);data(plain);finish(plain);data(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh unobserved ALL5 STORE mirror');
  }
  const report={native:true,keys,all105Program56MsHeld:true,other14RegistersHeld:true,
    CBefore:before.registers[12],CAfter:after.registers[12],writers,
    initialWorkingA:word(entry.state.ik1302.r),observerIndependent:mirror,
    ordinaryCSignFCreated:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,entry,prefix,second,end};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(capture({log:false})));
  else {capture();console.log('PASS native digit1/STORE C: actual D4(Y)/sign0, C=1, '
    +'program/Ms/14 other registers held and fresh full mirror.');}
}
module.exports={capture,finish,keys};
