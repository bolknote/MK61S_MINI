#!/usr/bin/env node
'use strict';
// Historical low-resource single-pair path: after capturing V, recover
// p/v into the live stack, place marker in T, try the existing E9(V).
// Fixed public keys only. No controllers, ROM, phase or RAM repair.
const assert=require('node:assert/strict');
const p=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
function operation(c,o,record=()=>{}) {
  const act=(name,keys)=>{record(name);c.pressSequence(keys).runFrames(8);};
  p.finish(c,o,record);
  act('capture-third',['П→X','0']);act('capture-fourth',['П→X','0']);
  act('recover-p1',['F',',']);act('recover-p2',['F',',']);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries()) {
    record('new-marker'+i);c.press(k).runFrames(12);
  }
  act('move-marker1',['П→X','0']);act('move-marker2',['П→X','0']);
  for(let i=0;i<3;i++)act('rotate-to-T'+(i+1),['F',',']);
  act('write-with-sign',['K','5']);return c;
}
function run() {
  const options={incoming:'101',fullUpper:['1111','2222','3333','4444']};
  const r=p.run(options,operation);
  const plain=p.prepare(options);operation(plain,options);plain.runFrames(3);aligned(plain);
  assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)),'unobserved full native mirror');
  const expected=r.beforeRegisters[0],oldV=r.before.V.slice(2);
  const stages=r.traced.events.filter(e=>e.ring&&['rotate-to-T1','rotate-to-T2','rotate-to-T3','write-with-sign','done'].includes(e.stage))
    .filter((e,i,a)=>a.findIndex(x=>x.stage===e.stage)===i)
    .map(e=>({stage:e.stage,visible:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,raw(e.ring[n])])),
      Ms:Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(e.ring[n])]))}));
  console.log(JSON.stringify({expected,oldV,ordinary0:r.afterRegisters[0],MsV:r.after.V.slice(2),
    changedOrdinary:r.afterRegisters.flatMap((v,i)=>v===r.beforeRegisters[i]?[]:[i]),
    changedMs:Object.fromEntries(Object.entries(r.after).filter(([n,v])=>v!==r.before[n])),
    programHeld:JSON.stringify(r.afterProgram)===JSON.stringify(r.beforeProgram),stages,
    writes:r.traced.events.filter(e=>e.stage==='write-with-sign'&&[0xEE,0xE9,0xE7,0xA3].includes(e.ip))
      .map(e=>({ip:e.ip.toString(16),slot:e.slot,read:e.raw,A:raw(e.r,0)})),
    rotationRequests:r.traced.events.filter(e=>e.stage.startsWith('rotate-to-T')&&e.ip===0xA3)
      .map(e=>({stage:e.stage,slot:e.slot,old:e.raw,request:raw(e.r,0)})),
    boundary:'measured one-pair continuation diagnostic; any collateral data loss disqualifies full K1'}));
}
if(require.main===module)run();
module.exports={operation,run};
