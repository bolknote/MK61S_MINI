#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-vw-upper-write.cjs');
const nop=require('./k1-vw-nop-read-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {M1_SLOTS,snapshotFromRing}=require('./k1-permutation-oracle.cjs');
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
function check(r,endStage='done') {
  if(endStage==='done')same(r.options.afterWrite??[],[]);
  else {
    const end=checks.boundary(r,endStage);
    r={...r,after:Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(end.ring[n],1,14)])),
      afterRegisters:M1_SLOTS.map(n=>raw(end.ring[n],0)),
      traced:{...r.traced,events:r.traced.events.filter(e=>e.command<=end.command),
        writes:r.traced.writes.filter(e=>e.command<end.command)}};
  }
  const prefix=nop.check(r,'short','nop/tail-0');
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const at=checks.boundary(r,'nop/tail-0'),end=checks.boundary(r,endStage);
  const es=r.traced.events.filter(e=>e.stage==='nop/tail-0');
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2));
  const early=es.find(e=>e.ip===0xEE&&e.nextIp!==0xE3);assert.ok(early);
  same([early.slot,early.raw,early.nextIp],['W',a,0xAB]);
  const load=es.find(e=>e.ip===0xD6);assert.ok(load);
  same([load.slot,raw(load.m,0)],['U',w]);same(load.sp.slice(0,2),[0xA7,0xAC]);
  same(es.filter(e=>e.command>=load.command&&e.command<=load.command+15).map(e=>[e.ip,e.slot]),[
    [0xD6,'U'],[0xA7,'V'],[0xE5,'W'],[0xE5,'Q'],[0xE5,'P7'],[0xE5,'P8'],
    [0xE5,'P9'],[0xE5,'P10'],[0xE5,'marker'],[0xE6,'control'],[0xE8,'X1'],
    [0xE7,'X'],[0xA8,'Y'],[0xA8,'Z'],[0xA8,'T'],[0xA9,'U']]);
  const push=checks.exactPush(r,'nop/tail-0',['X','Y','Z','T']);
  same(push.displaced,'9990FFFFFFF0');
  const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(lateRead);
  same([lateRead.slot,lateRead.raw],['X',w]);
  const lateWrite=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);assert.ok(lateWrite);
  repack.exactCopy(r,lateWrite,'P7',w);
  same(es.filter(e=>[0xE9,0xA3].includes(e.ip)),[],'no request or saved-X overwrite');
  for(const x of r.traced.writes.filter(x=>x.command>=at.command&&x.before!==x.value)) {
    const i=x.command-push.command;
    assert.ok(x.chip===3&&x.nibble%3===1&&x.nibble<37&&
      ((i>=0&&i<4&&x.slot===['X','Y','Z','T'][i])||
       (x.command===lateWrite.command&&x.slot==='P7')),
      'undeclared changed tetra in complete ordinary-to-upper write: '+JSON.stringify(x));
  }
  same(values(end),{...values(at),X:w,Y:'000010000000',Z:u,T:q,P7:w});
  same(raw(end.ring.W),a,'old upper word remains saved in W');
  same(raw(end.ring.Q),r.beforeRegisters[0]);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['V','marker']);
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  same(new Set(snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words).size,23);
  return {prefix,boundaries:rows.length,load:load.command,push,lateRead:lateRead.command,
    lateWrite:lateWrite.command,ordinaryP0DuplicatedInUpperP7:true,oldUpperP7SavedInW:true,
    all23HeldAtActionBoundaries:true,other14OrdinaryProgramAndServiceHeld:true,
    onlyExtraMarker:'V',lowerUandQStillOnlyInVisibleStack:true,
    normalStoredBankContract:false,workingExit:false,fullK1:false};
}
function negativeClear(r) {
  same(r.options.afterWrite,[['K','×']]);
  const prefix=check(r,'write/tail-0');
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const at=checks.boundary(r,'write/tail-0'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='write/tail-0');
  const w=r.before.W.slice(2),p=r.beforeRegisters[0];
  const gate=es.find(e=>e.ip===0x9C),read=es.find(e=>e.ip===0xEE);
  same([gate.slot,gate.raw,gate.nextIp],['W',r.before.P7.slice(2),0x9E]);
  same([read.slot,read.raw,read.nextIp],['X',w,0xA1]);
  const copy=es.find(e=>e.ip===0xE9);repack.exactCopy(r,copy,'Q',w);
  const request=es.find(e=>e.ip===0xA3);assert.ok(request);same(request.slot,'control');
  const expected=ringAt(r,request.command);
  for(const [j,v] of [[34,2],[31,8],[28,parseInt(w[2],16)]])expected.control[j]=v;
  same(ringAt(r,request.command+1),expected);
  same(r.traced.writes.filter(x=>x.command===request.command).map(x=>[x.chip,x.slot,x.nibble]),
    [[3,'control',28],[3,'control',31],[3,'control',34]]);
  const late=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(late);
  same([late.slot,late.raw],['X',w]);
  const final=es.find(e=>e.command>late.command&&e.ip===0xE7);repack.exactCopy(r,final,'P7',w);
  for(const x of r.traced.writes.filter(x=>x.command>=at.command&&x.before!==x.value))
    assert.ok(x.chip===3&&((x.command===copy.command&&x.slot==='Q'&&x.nibble%3===1&&x.nibble<37)||
      (x.command===request.command&&x.slot==='control'&&[28,31,34].includes(x.nibble))),
      'unexpected change in rejected K× suffix: '+JSON.stringify(x));
  same(values(end),{...values(at),Q:w,control:'28'+w[2]+'000000000'});
  same(repack.boundaryLosses(r).filter(e=>e.missing.length).map(e=>[e.stage,e.missing]),[['done',[p]]]);
  return {prefix,rejected:'without T marker K× writes Q, not V',read:read.command,
    overwriteQ:copy.command,request:request.command,lateRedundantCopy:final.command,
    lost:'original ordinary P0',extraMarkerVRemains:true,notGeneralImpossibility:true};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_UPPER_WRITE_OPTIONS||'{}');
  if(process.env.K1_UPPER_WRITE_NEGATIVE_CLEAR)o.afterWrite=[['K','×']];
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS upper write:',JSON.stringify(
    process.env.K1_UPPER_WRITE_NEGATIVE_CLEAR?negativeClear(r):check(r)));
  if(process.env.K1_UPPER_WRITE_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check,negativeClear};
