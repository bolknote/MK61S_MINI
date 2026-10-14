#!/usr/bin/env node
'use strict';
// Ordinary digit input exposes a genuine working-A maskF. Only public
// keys/frames act on the reference; snapshots and ring observers are passive.
// This is not a saved numeric signF or a preserving program-cache export.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const word=(a,lane)=>Array.from({length:12},(_,i)=>
  a[lane+3*i].toString(16).toUpperCase()).join('');
const data=c=>({program:Array.from({length:105},(_,i)=>c.readCommand(i)),
  ms:fullMsPages(c),registers:Array.from({length:15},(_,i)=>rawMemoryRegister(c,i))});

function prepare() {
  const c=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    c[name]=()=>{throw Error('Forbidden state setter: '+name);};
  return aligned(c);
}
function finish(c) {c.press('1').runFrames(2);aligned(c);}

function capture({mirror=true,log=true}={}) {
  const c=prepare(),before=data(c),prefix=[];
  let started=false,done=false,afterWriter=false;
  const result=trace(c,finish,{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    eventFilter:()=>!done,
    otherChipsAt:e=>{
      if(!started&&e.ip===0x91&&e.r[24]===15)started=true;
      if(started) {
        prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
        if(afterWriter)done=true;
        if(e.ip===0xE7)afterWriter=true;
      }
      return false;
    },
  });
  assert.ok(started&&done,'complete first mask91 to numeric writer, plus next boundary');
  assert.ok(prefix.every((e,i)=>!i||e.command===prefix[i-1].command+1));
  assert.equal(word(prefix[0].state.ik1302.r,0),'FFFFFFF0FFFF');
  const source=prefix[0].state.ik1302;
  const doubleCall=[0x91,0x92,0x93,0x94,0x95,0x98,0x9A,0x93,0x94,0x95,0x98,0x9A];
  assert.deepEqual(prefix.slice(0,12).map(e=>e.ip),doubleCall);
  assert.equal(prefix[12].ip,0x8D);
  assert.equal(word(prefix[12].state.ik1302.r,0),'FFFFFFF0FFFF');
  assert.equal(word(prefix[12].state.ik1302.st,1),word(source.r,2));
  const writer=prefix.at(-2);
  assert.equal(writer.ip,0xE7);assert.equal(writer.slot,'X');
  assert.equal(word(writer.state.ik1302.r,0),'000000010000');
  assert.equal(writer.state.ik1302.r[24],0);
  // A/B/C exchanges inside91 are NOT erasure: the mask returns intact.
  // Describe the later A8 replacement, not a global disappearance of F.
  const replacementIndex=prefix.findIndex((e,i)=>i>12&&e.state.ik1302.r[24]!==15);
  const replacement=prefix[replacementIndex];
  assert.ok(replacement&&replacement.command<writer.command);
  assert.equal(prefix[replacementIndex-1].ip,0xF4);
  assert.equal(replacement.ip,0xF6);
  assert.equal(replacement.state.ik1302.r[21],15,'native A7 is already the D4 sign-feed positionF');
  assert.equal(replacement.state.ik1302.r[24],1,'A8 is shifted digit1, not a globally erased mask');
  assert.ok(!prefix.some(e=>[0xD4,0xC7,0xC8].includes(e.ip)));
  const after=data(c);
  assert.deepEqual(after,before,'program/Ms/all15 ordinary words held; working X alone receives1');
  assert.equal(c.displayText(),'1,');
  if(mirror) {
    const plain=prepare();data(plain);finish(plain);data(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh unobserved ALL5 mirror');
  }
  const report={native:true,keys:['1'],source:'ordinary working-A digit mask, not M2 marker',
    sourceA:word(source.r,0),sourceASign:source.r[24],inletA:word(prefix[12].state.ik1302.r,0),
    sourceC:word(source.r,2),middleST:word(prefix[12].state.ik1302.st,1),
    firstA8ReplacementBeforeIp:replacement.ip,causingIp:prefix[replacementIndex-1].ip,
    replacementOffset:replacement.command-prefix[0].command,
    replacementA:word(replacement.state.ik1302.r,0),nativeD4SignFeedF:true,
    writerSlot:'X',writerA:word(writer.state.ik1302.r,0),writerSign:0,
    all105Program56Ms15RegistersHeld:true,ordinaryCSignFCreated:false,
    observerIndependent:mirror,transitions:prefix.length-1,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,prefix};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(capture({mirror:true,log:false})));
  else {capture();console.log('PASS native digit maskF, control-word middle-ST copy and fresh ALL5 mirror; '
    +'the actual writer receives ordinary1/sign0, not signF or program bytes.');}
}
module.exports={prepare,finish,capture};
