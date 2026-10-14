#!/usr/bin/env node
'use strict';
// Two ROM-directed physical controls, not a key-sequence search.
// Moving the ordinary pointer from P8/marker to P2/W was predicted to
// move a DA D4 destination from P3/Q to PC/Y. The native branch changes
// instead: P2 reaches DB/header2/D2. No metadata is injected.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const marker=require('./probe_a8_marker_route.cjs');
const {install,fixtures}=require('./check_partial_k2_program_scan.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const registers=c=>Array.from({length:15},(_,i)=>rawMemoryRegister(c,i));

function prepare({register=2}={}) {
  assert.ok([2,8].includes(register),'only the predicted target and original control');
  const c=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    c[name]=()=>{throw Error('Forbidden state setter: '+name);};
  install(c,fixtures[1]);preparePayload('8.7654321E-91',c);
  const program=marker.PROGRAM.slice(),keys=marker.PROGRAM_KEYS.slice();
  program[3]=0x40+register;keys[6]=String(register);
  c.pressSequence(['В/О','F','ВП',...keys,'F','/-/','В/О']);
  assert.deepEqual(program.map((_,i)=>c.readCommand(i)),program);
  c.inputNumber('1.0000001',{clear:true}).pressSequence(['X→П','0']);
  c.inputNumber('1.0000005E4',{clear:true}).pressSequence(['X→П','1']);
  c.pressSequence(['В/О','С/П']).runFrames(20);aligned(c);
  assert.equal(rawMemoryRegister(c,register),'9990FFFFFFF0');
  c.pressSequence(['F','/-/','Сx','БП','0','0']).runFrames(4);aligned(c);
  assert.equal(c.programCounter(),'00');
  assert.equal(rawMemoryRegister(c,register),'9990FFFFFFF0');
  return c;
}

function finish(c,{register=2,phaseOffset=0}={}) {
  assert.ok([2,8].includes(register));
  assert.ok(Number.isInteger(phaseOffset)&&phaseOffset>=0&&phaseOffset<=2);
  c.runFrames(phaseOffset).pressSequence(['K','ПП',String(register)]);aligned(c);
}

function capture({register=2,phaseOffset=0,mirror=true,log=true}={}) {
  const options={register,phaseOffset},c=prepare(options);
  const before={program:listing(c),ms:fullMsPages(c),registers:registers(c)};
  const prefix=[];let started=false;
  const t=trace(c,c=>finish(c,options),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    otherChipsAt:e=>{
      if(e.ip===0x73&&!prefix.length)started=true;
      if(started&&prefix.length<65)
        prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
  });
  const es=t.events,start=es.findIndex(e=>e.ip===0x73);
  assert.ok(start>=0);
  const load=es.findLastIndex((e,i)=>i<start&&e.ip===0xD6);
  assert.ok(load>=0);
  const selected=es.slice(start,start+10),sourceEvents=es.slice(load,start+10);
  assert.ok(sourceEvents.every((e,i)=>!i||e.command===sourceEvents[i-1].command+1));
  assert.equal(prefix.length,65);
  assert.ok(prefix.every((e,i)=>!i||e.command===prefix[i-1].command+1));
  assert.deepEqual(t.primitives,[],'neither control invokes the program reader');
  const after={program:listing(c),ms:fullMsPages(c),registers:registers(c)};
  const changes=before.registers.flatMap((value,index)=>value===after.registers[index]?[]:
    [{register:index,before:value,after:after.registers[index]}]);
  assert.deepEqual(after.program,before.program,'ALL105 program bytes held');
  assert.deepEqual(after.ms,before.ms,'ALL56 Ms bytes held');
  assert.equal(rawMemoryRegister(c,12),'000000000000','ordinary PC sign remains0');
  if(register===2) {
    assert.equal(es[load].slot,'W');
    assert.deepEqual(selected.map(e=>e.ip),[0x73,0x75,0xCA,0xDB,0xDC,0xDE,0xD2,0x30,0x30,0x30]);
    assert.equal(selected[6].slot,'Y','the relevant writer now arrives at ordinary PC');
    assert.equal(selected[4].r[34],2);
    assert.deepEqual(changes,[{register:2,before:'9990FFFFFFF0',after:'9990FFFFFFE9'}]);
    assert.ok(!es.some(e=>e.ip===0xD4&&e.slot==='Y'),'no native sign-writing D4 at PC');
  } else {
    assert.equal(es[load].slot,'marker');
    assert.deepEqual(selected.map(e=>e.ip),[0x73,0x75,0xCA,0xDA,0xDC,0xDE,0xD4,0xDD,0xD4,0x76]);
    assert.equal(selected[4].r[34],4);
    assert.deepEqual(changes,[
      {register:3,before:'000000000000',after:'79090FFFFFFE'},
      {register:5,before:'000000000000',after:'F79090FFFFFF'},
    ]);
  }
  assert.equal(c.ik1302.r[36]+16*c.ik1302.r[39],0x35);
  const stable=machineSnapshot(c);c.runFrames(3);aligned(c);
  assert.deepEqual(machineSnapshot(c),stable,'one whole phase-aligned idle period');
  assert.deepEqual(registers(c),after.registers);
  assert.deepEqual(listing(c),after.program);assert.deepEqual(fullMsPages(c),after.ms);
  if(mirror) {
    const plain=prepare(options);finish(plain,options);
    assert.deepEqual(machineSnapshot(plain),stable,'fresh unobserved ALL5-chip mirror');
  }
  const report={register,phaseOffset,pointer:before.registers[register],
    sourceSlot:es[load].slot,sourceMacros:sourceEvents.length-1,
    path:selected.map(e=>e.ip),nativeR33:selected[0].r[33],
    nativeR27:selected[0].r[27],nativeR30:selected[0].r[30],
    nativeHeader:selected[4].r[34],writerSlot:selected[6].slot,
    registerChanges:changes,all105ProgramBytesHeld:true,all56MsBytesHeld:true,
    ordinaryPCSign:0,observerIndependent:mirror,idleStable:true,
    nativeSignFCreated:false,programCacheExport:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,sourceEvents,selected,prefix,before,after};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(
    [2,8].map(register=>capture({register,mirror:false,log:false}))));
  else {
    for(const register of [2,8])capture({register});
    console.log('PASS predicted P2/W destination control AND original P8/marker DA control; '
      +'fresh ALL5 mirrors, ALL105/56 held. Native P2 takes DB/header2/D2, not sign-F D4.');
  }
}
module.exports={prepare,finish,capture};
