#!/usr/bin/env node
'use strict';
// A ROM-directed logical-address construction, NOT a random key search.
// Only real keys change the native reference; no detached hypotheses here.
// This establishes DA entry with marker data, NOT a program-cache export.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const marker=require('./probe_a8_marker_route.cjs');
const {install,fixtures}=require('./check_partial_k2_program_scan.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {layout}=require('./cache-d4-native-topology.cjs');
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const registers=c=>Array.from({length:15},(_,i)=>rawMemoryRegister(c,i));
const raw=[0,3,9,12,18,21];
const wordTetras=s=>[...s].reverse().map(v=>parseInt(v,16));

function prepare({markerKind='logical',fixture=fixtures[1],calc=new MK61(),
  values='8.7654321E-91'}={}) {
  assert.ok(['logical','classic'].includes(markerKind));
  const c=calc;
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    c[name]=()=>{throw Error('Forbidden state setter: '+name);};
  // Install the raw-code fixture before the abnormal-number preparation.
  // Attempting to programme it after that preparation is NOT reliable.
  install(c,fixture);
  marker.prepare({calc:c,values,markerKind});
  const pointer=markerKind==='logical'?'9990FFFFFFF0':'0000F0000000';
  assert.equal(rawMemoryRegister(c,8),pointer);
  c.pressSequence(['F','/-/','Сx','БП','0','0']).runFrames(4);aligned(c);
  assert.equal(c.programCounter(),'00');
  assert.equal(rawMemoryRegister(c,8),pointer);
  return c;
}

function finish(c,{phaseOffset=0}={}) {
  assert.ok(Number.isInteger(phaseOffset)&&phaseOffset>=0&&phaseOffset<=2);
  c.runFrames(phaseOffset).pressSequence(['K','ПП','8']);aligned(c);
}

function capture({phaseOffset=0,markerKind='logical',mirror=true,log=true}={}) {
  assert.ok(markerKind==='logical'||phaseOffset===0,'classic negative control only at phase0');
  const c=prepare({markerKind}),before={program:listing(c),ms:fullMsPages(c),registers:registers(c)};
  const prefix=[];let collecting=false;
  const t=trace(c,c=>finish(c,{phaseOffset}),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    otherChipsAt:e=>{
      if(e.ip===0x73&&!prefix.length)collecting=true;
      if(collecting&&prefix.length<65)
        prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
  });
  const es=t.events,start=es.findIndex(e=>e.ip===0x73);
  assert.ok(start>=0,'the native indirect operation actually reaches73');
  const gate=es.findLastIndex((e,i)=>i<start&&e.ip===0x26);
  assert.ok(gate>=2);
  const origin=es.slice(gate-2,start+5),selected=es.slice(start,start+10);
  const load=es.findLastIndex((e,i)=>i<gate&&e.ip===0xD6);
  assert.ok(load>=0,'native raw pointer is loaded byD6');
  const sourceEvents=es.slice(load,start+10);
  assert.ok(sourceEvents.every((e,i)=>!i||e.command===sourceEvents[i-1].command+1));
  assert.equal(origin[0].ip,0xDD);
  assert.equal(origin[0].sp[0],0x26);
  assert.equal(es[start].pc,0);
  assert.equal(es[start].r[33],origin[0].r[3]);
  const da=es[start+3].ip===0xDA;
  const after={program:listing(c),ms:fullMsPages(c),registers:registers(c)};
  const changes=before.program.flatMap((value,address)=>value===after.program[address]?[]:
    [{address,before:value,after:after.program[address]}]);
  const regChanges=before.registers.flatMap((value,index)=>value===after.registers[index]?[]:
    [{register:index.toString(16).toUpperCase(),before:value,after:after.registers[index]}]);
  assert.equal(c.ik1302.r[36]+16*c.ik1302.r[39],0x35);
  assert.deepEqual(t.primitives,[],'no C8/program-cache reader in the fixed control');
  assert.equal(prefix.length,65);
  assert.ok(prefix.every((e,i)=>!i||e.command===prefix[i-1].command+1));
  if(markerKind==='logical') {
    assert.equal(da,true,'the seven-F word supplies the missing nativeR33F');
    assert.deepEqual(selected.map(e=>e.ip),[0x73,0x75,0xCA,0xDA,0xDC,0xDE,0xD4,0xDD,0xD4,0x76]);
    assert.equal(selected[0].r[27],9,'native address high operand, NOT hypothetical2');
    assert.equal(selected[4].r[34],4,'native DA supplies D4 header4');
    const payload=raw.map(k=>selected[0].r[k]);
    assert.deepEqual(payload,[15,15,15,15,0,9],'marker-derived FF/FF/90, NOT fixtureA3/D4/B5');
    assert.deepEqual(raw.map(k=>selected[4].r[k]),payload);
    for(const [register,offset] of [[3,1],[5,0]]) {
      const values=wordTetras(after.registers[register]);
      assert.deepEqual(raw.map(k=>values[k/3+offset]),payload,
        'native exact raw6 physically retained in ordinaryP'+register);
    }
    assert.deepEqual(after.program,before.program,'ALL105 program bytes held');
    assert.deepEqual(after.ms,before.ms,'ALL56 Ms bytes held');
    assert.deepEqual(regChanges.map(e=>e.register),['3','5'],
      'earlier address write ultimately preservesP8; only export destinations change');
  } else {
    assert.equal(da,false,'a loneF does not supply the required sourceR3F');
    assert.equal(selected[4].r[34],3);
    assert.deepEqual(changes,[{address:37,before:0,after:0xF7}],
      'negative control programme damage is explicit, not a safe alternate entry');
    assert.deepEqual(regChanges.map(e=>e.register),['8']);
    assert.deepEqual(after.ms,before.ms);
  }
  const stable=machineSnapshot(c);
  c.runFrames(3);aligned(c);
  assert.deepEqual(machineSnapshot(c),stable,'one whole phase-aligned idle period is stable');
  assert.deepEqual(registers(c),after.registers);
  assert.deepEqual(listing(c),after.program);
  assert.deepEqual(fullMsPages(c),after.ms);
  if(mirror) {
    const plain=prepare({markerKind});finish(plain,{phaseOffset});
    assert.deepEqual(machineSnapshot(plain),stable,'fresh unobserved ALL5-chip mirror');
    assert.deepEqual(registers(plain),after.registers);
    assert.deepEqual(listing(plain),after.program);
    assert.deepEqual(fullMsPages(plain),after.ms);
  }
  const report={markerKind,phaseOffset,pointer:before.registers[8],keys:['K','ПП','8'],
    nativeDA:da,nativeHeader:selected[4].r[34],
    nativeTwoD4:da&&selected[4].r[34]===4,
    originR3:origin[0].r[3],nativeR33:selected[0].r[33],nativeR27:selected[0].r[27],
    raw3At73:raw.map(k=>selected[0].r[k]),programChanges:changes,registerChanges:regChanges,
    all56MsBytesHeld:JSON.stringify(before.ms)===JSON.stringify(after.ms),
    observerIndependent:mirror,phaseAlignedIdleStable:true,
    programReaderReached:false,nativeProgramCacheExport:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,mapping:layout(),origin,sourceEvents,selected,prefix,before,after};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(
    [...[0,1,2].map(phaseOffset=>capture({phaseOffset,mirror:false,log:false})),
      capture({markerKind:'classic',mirror:false,log:false})]));
  else {
    for(const phaseOffset of [0,1,2])capture({phaseOffset});
    capture({markerKind:'classic'});
    console.log('PASS native logical-pointer DA/header4/twoD4 in3 phases and3 ALL5-chip mirrors; '+
      'one explicit damaged-programme classic negative control with mirror; '+
      'no program-cache transport or partialK2.');
  }
}
module.exports={prepare,finish,capture};
