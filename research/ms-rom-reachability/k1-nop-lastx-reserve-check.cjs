#!/usr/bin/env node
'use strict';
// Exact negative control: the ordinary LastX entry is not the locally
// valid accepted-9C(Z) -> EE(Q) reserve path.
const assert=require('node:assert/strict');
const probe=require('./k1-nop-lastx-reserve.cjs');
const nop=require('./k1-vw-nop-read-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const values=e=>Object.fromEntries(Object.entries(e.ring).map(([n,t])=>[n,raw(t)]));
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,initialPhaseOffsetExcluded:true,assumedSuccessfulAttempts:1};
}
function rejected(r) {
  same(r.options.afterReserve??[],[]);
  assert.ok([0,1].includes(r.options.reserveLeadPhase));
  const prefix=nop.check(r,'short','reserve/lastx');
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  const at=checks.boundary(r,'reserve/lastx'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='reserve/lastx');
  const gates=es.filter(e=>e.ip===0x9C),read=es.find(e=>e.ip===0xEE);
  same(gates.length,1);same([gates[0].slot,gates[0].raw,gates[0].nextIp],
    ['U',r.before.V.slice(2),0x9E]);
  same([read.slot,read.raw,read.nextIp],['X1','00008FFFFFFF',0xF0]);
  const push=checks.exactPush(r,'reserve/lastx',['W','Q','P7','P8']);
  same(push.displaced,r.before.P8.slice(2));
  const late=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(late);
  same([late.slot,late.raw],['X','000010000000']);
  const final=es.find(e=>e.command>late.command&&e.ip===0xE7);
  repack.exactCopy(r,final,'X','000010000000');
  same(es.filter(e=>[0xE9,0xA3].includes(e.ip)),[]);
  for(const x of r.traced.writes.filter(x=>x.command>=at.command&&x.before!==x.value)) {
    const i=x.command-push.command;
    assert.ok(x.chip===3&&i>=0&&i<4&&x.slot===['W','Q','P7','P8'][i]&&x.nibble%3===1&&x.nibble<37,
      'undeclared changed tetra in rejected LastX: '+JSON.stringify(x));
  }
  const a=r.before.P7.slice(2),p=r.beforeRegisters[0];
  same(values(end),{...values(at),W:'00008FFFFFFF',Q:a,P7:p,P8:a});
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:r.before.W.slice(2)));
  same(repack.boundaryLosses(r).filter(e=>e.missing.length).map(e=>[e.stage,e.missing]),
    [['done',[r.before.P8.slice(2)]]]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['T','V','marker']);
  return {prefix,acceptedControl:gates[0].command,read:read.command,push,lateRead:late.command,
    lateCopy:final.command,lost:'old upper P8',readQ:false,
    other14OrdinaryProgramServiceAndUpperP9P10Held:true,
    rejectedCandidate:true,notGeneralImpossibility:true};
}
if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_NOP_RESERVE_OPTIONS||'{}')};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS rejected LastX reserve:',JSON.stringify(rejected(r)));
  if(process.env.K1_NOP_RESERVE_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,rejected};
