#!/usr/bin/env node
'use strict';
// Ordinary STORE C control after the REAL short-A8 call. No extra marker
// is injected; the conditional reserve lives only in a separate model.
const assert=require('node:assert/strict');
const driver=require('./probe_a8_seven_source.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const registers=c=>Array.from({length:15},(_,i)=>rawMemoryRegister(c,i));
const keys=['X→П','ВП']; // register C: the EXP key, not a digit-key timing trick.

function ready() {
  const c=driver.prepare();driver.finish(c);aligned(c);return c;
}
function finish(c) {c.pressSequence(keys).runFrames(2);aligned(c);}
function auto(c) {c.pressSequence(['F','/-/']).runFrames(2);aligned(c);}

function modeCapture({mirror=true,log=true}={}) {
  const c=ready();
  c.pressSequence(['F','ВП']).runFrames(2);aligned(c);
  assert.equal(c.ik1302.r[2],0,'native F PROGRAM control, not the malformed F state');
  const entry={command:0,state:machineSnapshot(c)},before=listing(c);
  finish(c);
  const programStoreEnd={command:3360,state:machineSnapshot(c)},program=listing(c);
  const changes=program.flatMap((v,i)=>v===before[i]?[]:[{address:i,before:before[i],after:v}]);
  assert.equal(changes.length,1);assert.equal(changes[0].after,0x4C);
  auto(c);
  const autoEnd={command:6720,state:machineSnapshot(c)};
  assert.equal(c.ik1302.r[2],8,'native F AUTO control');
  const beforeLast={ms:fullMsPages(c),program:listing(c),registers:registers(c)};
  finish(c);
  const end={command:10080,state:machineSnapshot(c)};
  assert.deepEqual({ms:fullMsPages(c),program:listing(c),registers:registers(c)},beforeLast);
  if(mirror) {
    const plain=ready();plain.pressSequence(['F','ВП']).runFrames(2);aligned(plain);
    listing(plain);finish(plain);listing(plain);auto(plain);
    fullMsPages(plain);listing(plain);registers(plain);finish(plain);
    fullMsPages(plain);listing(plain);registers(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh public mode-repair ALL5 mirror');
  }
  const report={native:true,programStoreWritesCode4C:true,programChanges:changes,
    nativeProgramR2:0,nativeAutoR2:8,autoStoreHoldsProgramMsRegisters:true,
    malformedR2FNotEquatedWithProgramMode:true,observerIndependent:mirror};
  if(log)console.log(JSON.stringify(report));
  return {report,entry,programStoreEnd,autoEnd,end};
}

function capture({mirror=true,log=true}={}) {
  const c=ready(),before={ms:fullMsPages(c),program:listing(c),registers:registers(c)};
  const entry={command:0,state:machineSnapshot(c)},prefix=[],writes=[];
  trace(c,finish,{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:()=>prefix.length<65,
    otherChipsAt:e=>{
      prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
    onWrite:w=>{if(w.chip===3&&w.ip===0xD4&&w.nibble===24)writes.push(w);},
  });
  const end={command:3360,state:machineSnapshot(c)};
  const after={ms:fullMsPages(c),program:listing(c),registers:registers(c)};
  assert.equal(prefix.length,65);
  assert.deepEqual(after,before,'normal STORE C copies X=0; other data/program/Ms held');
  assert.equal(after.registers[12],'000000000000');
  assert.ok(writes.some(w=>w.slot==='Y'&&w.value===0),'ordinary C writer was really called');
  if(mirror) {
    const plain=ready();fullMsPages(plain);listing(plain);registers(plain);
    finish(plain);fullMsPages(plain);listing(plain);registers(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh STORE C ALL5 mirror');
  }
  const report={native:true,keys,frames:6,CBefore:before.registers[12],CAfter:after.registers[12],
    all105ProgramAnd56MsHeld:true,all15OrdinaryWordsHeld:true,observerIndependent:mirror,
    CSignFCreated:false,extraMarkerCreated:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,entry,prefix,end,writes};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify({
    ...capture({mirror:false,log:false}),modeControl:modeCapture({mirror:false,log:false})}));
  else {capture();console.log('PASS native ordinary STORE C control and fresh ALL5 mirror; '
    +'C=0, program/Ms/15 ordinary words held, no signF or marker injection.');
    modeCapture();console.log('PASS native PROGRAM STORE/F AUTO/STORE control and full mirror.');}
}
module.exports={ready,finish,capture,modeCapture,keys};
