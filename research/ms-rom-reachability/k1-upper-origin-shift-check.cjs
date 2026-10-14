#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-upper-origin-shift.cjs');
const reader=require('./k1-vw-upper-read-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
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
function shift(r,negative=false) {
  // A zero-frame phase label has no native command/event. The next action's
  // first event is the same completed read, plus any declared idle frames.
  const prefix=reader.read(r,'origin/shift');
  const push=checks.exactPush(r,'origin/shift',negative?
    ['P7','P8','P9','P10']:['P8','P9','P10','marker']);
  same(push.displaced,negative?r.before.P10.slice(2):'000FFFFFFFFF');
  const es=r.traced.events.filter(e=>e.stage==='origin/shift');
  const load=es.find(e=>e.ip===0xD6);assert.ok(load);
  same([load.slot,raw(load.m,0)],negative?['marker',r.beforeRegisters[8]]:['U',r.before.W.slice(2)]);
  same(load.sp.slice(0,2),[0xA7,0xAC]);
  if(!negative) {
    const route=es.filter(e=>e.command>=load.command&&e.command<load.command+10);
    same(route.map(e=>[e.ip,e.slot]),[
      [0xD6,'U'],[0xA7,'V'],[0xE5,'W'],[0xE6,'Q'],[0xE8,'P7'],
      [0xE7,'P8'],[0xA8,'P9'],[0xA8,'P10'],[0xA8,'marker'],[0xA9,'control']]);
    same(route[2].m[22],15);
  }
  const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(lateRead);
  const late=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);assert.ok(late);
  same([lateRead.slot,lateRead.raw,late.slot],negative?
    ['P7',r.beforeRegisters[8],'X']:['P7',r.before.P7.slice(2),'P7']);
  repack.exactCopy(r,late,late.slot,lateRead.raw);
  return {prefix,load:load.command,loadSlot:load.slot,push,lateRead:lateRead.command,
    lateSource:lateRead.slot,lateValue:lateRead.raw,lateWrite:late.command,lateTarget:late.slot};
}
function check(r,endStage='done') {
  if(endStage==='done')same(r.options.afterOrigin??[],[]);
  checks.protectedFields(r,[0],Object.keys(r.before));
  const prefix=shift(r),at=checks.boundary(r,'origin/shift'),end=checks.boundary(r,endStage);
  const [u,v,w,q,a,b,c,d]=['U','V','W','Q','P7','P8','P9','P10'].map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0],want={...values(at),marker:d,P8:w,P9:b,P10:c};
  same(values(end),want);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['V','W']);
  same(snapshotFromRing(end.ring).words.slice(0,15),r.beforeRegisters.map((x,i)=>i?x:a));
  if(endStage==='done')same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:a));
  const storeEvents=r.traced.events.filter(e=>e.stage==='origin/save');
  const source=storeEvents.find(e=>e.ip===0xEE&&e.nextIp!==0xE3);assert.ok(source);
  same([source.slot,source.raw],['P7',a]);
  const write=storeEvents.find(e=>e.ip===0xD4);assert.ok(write);
  same(write.slot,'U');
  const expected=ringAt(r,write.command);
  same(raw(expected.U,0),w);same(raw(expected.P8),w,'ordinary P0 may change only after its old word is stored');
  for(let j=0;j<12;j++)expected.U[3*j]=parseInt(a[11-j],16);
  same(ringAt(r,write.command+1),expected,'exact twelve-tetra ordinary write among all 630 tetras');
  same(r.traced.writes.filter(w=>w.command===write.command).map(w=>[w.chip,w.slot,w.nibble]),
    Array.from({length:12},(_,j)=>[3,'U',3*j]));
  for(const w of r.traced.writes.filter(w=>w.command>=at.command&&
    (endStage==='done'||w.command<end.command)&&w.before!==w.value)) {
    const i=w.command-prefix.push.command;
    assert.ok(w.chip===3&&((i>=0&&i<4&&w.slot===['P8','P9','P10','marker'][i]&&
      w.nibble%3===1&&w.nibble<37)||(w.command===write.command&&w.slot==='U'&&w.nibble%3===0&&w.nibble<36)),
      'undeclared changed tetra in complete origin suffix: '+JSON.stringify(w));
  }
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  same(new Set(original).size,23);
  const seen=new Set();let boundaries=0,markerBoundaries=0;
  for(const e of r.traced.events)if(e.ring&&e.command<=end.command&&!seen.has(e.stage)) {
    seen.add(e.stage);boundaries++;
    const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    if(e.command>prefix.push.command) {
      same(raw(e.ring.marker),d);live.push(d);markerBoundaries++;
    }
    for(const x of original)assert.ok(live.includes(x),'lost '+x+' at '+e.stage);
  }
  // Do not silently weaken the normal 23-word oracle: d is outside that
  // storage contract, at a precisely identified temporary physical place.
  const oldOracle=repack.boundaryLosses(r).filter(e=>seen.has(e.stage)&&e.missing.length);
  assert.ok(oldOracle.length);for(const e of oldOracle)same(e.missing,[d]);
  same(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[a,'000010000000',u,q]);
  same(['U','V','W','Q'].map(n=>raw(end.ring[n])),[v,'9990FFFFFFF0','9990FFFFFFF0',p]);
  return {boundaries,all23HeldAtActionBoundariesIncludingTemporaryMarkerSlot:true,markerBoundaries,
    prefix,ordinarySave:{read:source.command,source:source.slot,write:write.command},
    lastUpperInPhysicalMarker:true,other14OrdinaryProgramAndServiceHeld:true,
    normalStoredBankContract:false,workingExit:false,fullK1:false};
}
function lastXLoss(r) {
  same(r.options.afterOrigin,[['F','В↑']]);
  const prefix=check(r,'origin/tail-0'),es=r.traced.events.filter(e=>e.stage==='origin/tail-0');
  const [a,b,c,d]=['P7','P8','P9','P10'].map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0],w=r.before.W.slice(2),before=checks.boundary(r,'origin/tail-0');
  const end=checks.boundary(r,'done'),push=checks.exactPush(r,'origin/tail-0',['P7','P8','P9','P10']);
  same(push.displaced,c);
  const early=es.find(e=>e.ip===0xEE&&e.nextIp!==0xE3);
  same([early.slot,early.raw],['Q',p]);
  same(values(end),{...values(before),P7:p,P8:a,P9:w,P10:b});
  same(raw(end.ring.marker),d);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:a));
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T','marker'].map(n=>raw(end.ring[n]))];
  const original=[...r.beforeRegisters,...Object.keys(r.before).map(n=>r.before[n].slice(2))];
  same(original.filter(x=>!live.includes(x)),[c]);
  return {prefix,rejected:'LastX backs up old P0 at the cost of the only old P9 word',
    earlyRead:early.command,push,lastUpperStillInMarker:true,lost:'original upper P9',
    notGeneralImpossibility:true};
}
function negative(r) {
  same(r.options.originLeadPhase,2);same(r.options.stopAfterShift,true);
  checks.protectedFields(r,[0],Object.keys(r.before));const path=shift(r,true);
  const bad=repack.boundaryLosses(r).filter(e=>e.missing.length);
  same(bad.map(e=>[e.stage,e.missing]),[['done',[r.before.P10.slice(2)]]]);
  const end=checks.boundary(r,'done');same(raw(end.ring.marker),'000FFFFFFFFF');
  return {rejected:'two extra frames select the other four-word push',path,
    lost:'last upper word',notGeneralImpossibility:true};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_ORIGIN_OPTIONS||'{}');
  if(process.env.K1_ORIGIN_NEGATIVE){o.originLeadPhase=2;o.stopAfterShift=true;}
  if(process.env.K1_ORIGIN_LASTX_NEGATIVE)o.afterOrigin=[['F','В↑']];
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);
  if(process.env.K1_ORIGIN_DIAGNOSTIC)console.log('DIAGNOSTIC:',JSON.stringify({
    end:values(checks.boundary(r,'done')),afterRegisters:r.afterRegisters,
    routes:r.traced.events.filter(e=>e.stage.startsWith('origin/')&&[0x9C,0xD6,0xD4,0xEE,0xE7,0xE9,0xA8].includes(e.ip))
      .map(e=>({stage:e.stage,n:e.command,ip:e.ip.toString(16),slot:e.slot,next:e.nextIp.toString(16),m:raw(e.m),a:raw(e.r,0),st:e.sp}))}));
  else console.log('PASS origin shift:',JSON.stringify(process.env.K1_ORIGIN_NEGATIVE?negative(r):
    process.env.K1_ORIGIN_LASTX_NEGATIVE?lastXLoss(r):check(r)));
  if(process.env.K1_ORIGIN_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,shift,check,negative,lastXLoss};
