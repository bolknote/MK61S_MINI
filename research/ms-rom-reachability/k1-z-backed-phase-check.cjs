#!/usr/bin/env node
'use strict';
// Negative timing controls. Fixed phase waits are not minimum human delays.
const assert=require('node:assert/strict');
const deep=require('./k1-z-backed-deep-entry.cjs');
const lastx=require('./k1-z-backed-lastx.cjs');
const audit=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b)=>assert.deepEqual(a,b);

function frame(which,phase) {
  const probe=which==='nop'?deep:lastx;
  const r=probe.run({deepTailPhases:which==='nop'?[phase]:[1,phase]});
  const lost=r.before[which==='nop'?'U':phase===0?'V':'P8'].slice(2);
  same(r.rows.filter(e=>e.missing.length).map(e=>[e.stage,e.missing]),
    [['immediate',[lost]],['done',[lost]]]);
  return {operation:which,extraFrames:phase,lost,negativeFixtureOnly:true};
}

function nativeNop() {
  const r=deep.traced({deepTailPhases:[0]}),stage='deep/tail-0';
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const at=checks.boundary(r,stage),end=checks.boundary(r,'done');
  const u=r.before.U.slice(2),p=r.beforeRegisters[0],es=r.traced.events.filter(e=>e.stage===stage);
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['V',0x9E],['control',0x9E]]);
  same(es.filter(e=>e.ip===0xEE).map(e=>[e.slot,e.raw,e.nextIp]),[['X',u,0xAB],['Q',p,0xE3]]);
  same(es.filter(e=>[0xE9,0xA3,0xA8].includes(e.ip)),[]);
  const late=es.filter(e=>e.ip===0xE7);same(late.length,1);repack.exactCopy(r,late[0],'X',p);
  same(r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.before!==w.value&&w.command!==late[0].command),[]);
  const expected=structuredClone(at.ring);audit.word(expected,'X',p);same(end.ring,expected);
  same(raw(at.ring.X),u);same(raw(end.ring.U),'9990FFFFFFF0');
  same(repack.boundaryLosses(r).filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),[['done',[u]]]);
  return {lateWrite:late[0].command,onlyXChanged:true,lost:u,
    unobserved:keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,deep.finish)};
}

function rotate(phase) {
  const r=lastx.run({deepTail:[['K','0'],['F','В↑'],['F',',']],deepTailPhases:[1,1,phase]});
  const lost=r.before[phase===0?'U':'V'].slice(2);
  same(r.rows.filter(e=>e.missing.length).map(e=>[e.stage,e.missing]),
    [['immediate',[lost]],['done',[lost]]]);
  return {operation:'F-comma after LastX',extraFrames:phase,lost,
    exactWriterNotAuditedHere:true,negativeFixtureOnly:true};
}

if(require.main===module) {
  const only=process.env.K1_Z_PHASE_CASE;
  for(const which of ['nop','lastx'])for(const phase of [0,2])if(!only||only===which+'-'+phase)
    console.log('PASS negative phase:',JSON.stringify(frame(which,phase)));
  for(const phase of [0,1,2])if(!only||only==='rotate-'+phase)
    console.log('PASS rejected direct cleanup:',JSON.stringify(rotate(phase)));
  if(!only||only==='native-nop')console.log('PASS exact negative NOP:',JSON.stringify(nativeNop()));
}
module.exports={frame,nativeNop,rotate};
