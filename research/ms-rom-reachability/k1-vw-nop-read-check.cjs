#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-vw-nop-read.cjs');
const deep=require('./k1-repack-deep-clone-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {M1_SLOTS}=require('./k1-permutation-oracle.cjs');
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
function check(r,kind='short',endStage='done') {
  if(endStage==='done')same(r.options.afterNop??[],[]);
  else {
    const end=checks.boundary(r,endStage);
    r={...r,after:Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(end.ring[n],1,14)])),
      afterRegisters:M1_SLOTS.map(n=>raw(end.ring[n],0)),
      traced:{...r.traced,events:r.traced.events.filter(e=>e.command<=end.command),
        writes:r.traced.writes.filter(e=>e.command<end.command)}};
  }
  const prefix=deep.check(r,'nop/read');
  const negative=kind==='phase',target=negative?'P8':kind==='short'?'W':'X';
  checks.protectedFields(r,[0],['U','V','W','Q',...(negative?['P8']:[])]);
  const at=checks.boundary(r,'nop/read'),end=checks.boundary(r,endStage);
  const es=r.traced.events.filter(e=>e.stage==='nop/read');
  const early=es.find(e=>e.ip===0xEE&&e.nextIp!==0xE3);assert.ok(early);
  same([early.slot,early.raw,early.nextIp],negative?['W','9990FFFFFFF0',0xAB]:['X','000010000000',0xAB]);
  const late=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(late);
  const value=negative?'000010000000':r.before.P7.slice(2);
  same([late.slot,late.raw],negative?['X',value]:['P7',value]);
  const copy=es.find(e=>e.command>late.command&&e.ip===0xE7);assert.ok(copy);
  repack.exactCopy(r,copy,target,value);
  same(es.filter(e=>[0xE9,0xA3,0xA8].includes(e.ip)),[],
    'no E9 write, secondary request, or stack push in the complete NOP action');
  for(const w of r.traced.writes.filter(w=>w.command>=at.command&&w.before!==w.value))
    assert.ok(w.command===copy.command&&w.chip===3&&w.slot===target&&w.nibble%3===1&&w.nibble<37,
      'only the declared late copy may change a tetra: '+JSON.stringify(w));
  same(values(end),{...values(at),[target]:value});
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:r.before.W.slice(2)));
  const rows=repack.boundaryLosses(r),bad=rows.filter(e=>e.missing.length);
  if(negative)same(bad.map(e=>[e.stage,e.missing]),[['done',[r.before.P8.slice(2)]]]);
  else same(bad,[]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),
    kind==='short'?['T','V','marker']:['T','V','W','marker']);
  return {kind,prefix,boundaries:rows.length,earlyRead:early.command,lateRead:late.command,
    lateWrite:copy.command,target,noVisiblePush:true,noE9OrRequest:true,
    all23HeldAtActionBoundaries:!negative,removedWMarker:kind==='short',
    workingExit:false,fullK1:false,negativeIsNotGeneralImpossibility:negative};
}
function clean(r,endStage='done') {
  if(endStage!=='done') {
    const end=checks.boundary(r,endStage);
    r={...r,after:Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(end.ring[n],1,14)])),
      afterRegisters:M1_SLOTS.map(n=>raw(end.ring[n],0)),
      traced:{...r.traced,events:r.traced.events.filter(e=>e.command<=end.command),
        writes:r.traced.writes.filter(e=>e.command<end.command)}};
  }
  same(r.options.afterNop,[['K','×'],['0']]);
  const prefix=check(r,'short','nop/tail-0');
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const at=checks.boundary(r,'nop/tail-0'),middle=checks.boundary(r,'nop/tail-1');
  const end=checks.boundary(r,endStage),es=r.traced.events.filter(e=>e.stage==='nop/tail-0');
  const ctrl=es.find(e=>e.ip===0x9C),read=es.find(e=>e.ip===0xEE);
  same([ctrl.slot,ctrl.nextIp],['W',0x9E]);
  same(ctrl.raw,r.before.P7.slice(2));
  same([read.slot,read.raw,read.nextIp],['X','000010000000',0xA1]);
  const copy=es.find(e=>e.ip===0xE9);repack.exactCopy(r,copy,'V','000010000000');
  const request=es.find(e=>e.ip===0xA3);assert.ok(request);same(request.slot,'control');
  const expected=ringAt(r,request.command);
  for(const [j,v] of [[34,2],[31,8],[28,0]])expected.control[j]=v;
  same(ringAt(r,request.command+1),expected,'only the neutral 28h header is written');
  same(r.traced.writes.filter(w=>w.command===request.command).map(w=>[w.chip,w.slot,w.nibble]),
    [[3,'control',28],[3,'control',31],[3,'control',34]]);
  const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
  same([lateRead.slot,lateRead.raw],['X','000010000000']);
  const late=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);
  repack.exactCopy(r,late,'X','000010000000');
  same(values(middle),{...values(at),V:'000010000000',control:'280000000000'});
  const push=checks.exactPush(r,'nop/tail-1',['X','Y','Z','T']);same(push.displaced,'9990FFFFFFF0');
  const finalWrite=r.traced.events.find(e=>e.stage==='nop/tail-1'&&e.ip===0xE7&&
    e.command>push.command+3);repack.exactCopy(r,finalWrite,'X','000000000000');
  for(const w of r.traced.writes.filter(w=>w.command>=at.command&&w.before!==w.value)) {
    const i=w.command-push.command;
    assert.ok(w.chip===3&&((w.command===copy.command&&w.slot==='V'&&w.nibble%3===1&&w.nibble<37)||
      (w.command===request.command&&w.slot==='control'&&[28,31,34].includes(w.nibble))||
      (i>=0&&i<4&&w.slot===['X','Y','Z','T'][i]&&w.nibble%3===1&&w.nibble<37)||
      (w.command===finalWrite.command&&w.slot==='X'&&w.nibble%3===1&&w.nibble<37)),
      'undeclared changed tetra in complete marker removal: '+JSON.stringify(w));
  }
  const u=r.before.U.slice(2),q=r.before.Q.slice(2);
  same(values(end),{...values(middle),X:'000000000000',Y:'000010000000',Z:u,T:q});
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker']);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:r.before.W.slice(2)));
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  return {prefix,boundaries:rows.length,control:ctrl.command,read:read.command,
    clearV:copy.command,request:request.command,push,clearX:finalWrite.command,
    allExtraMarkersRemoved:true,all23HeldAtActionBoundaries:true,
    lowerUandQStillOnlyInVisibleStack:true,normalStoredBankContract:false,workingExit:false,fullK1:false};
}
if(require.main===module) {
  const kind=process.env.K1_NOP_CASE??'short';assert.ok(['short','read','phase','clean'].includes(kind));
  const o=JSON.parse(process.env.K1_NOP_OPTIONS||'{}');
  if(kind==='short'||kind==='clean')o.fullUpper??=['-1E-99','9022','9033','9044'];
  if(kind==='clean')o.afterNop=[['K','×'],['0']];
  if(kind==='phase')o.nopLeadPhase=0;
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS NOP:',JSON.stringify(kind==='clean'?clean(r):check(r,kind)));
  if(process.env.K1_NOP_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check,clean};
