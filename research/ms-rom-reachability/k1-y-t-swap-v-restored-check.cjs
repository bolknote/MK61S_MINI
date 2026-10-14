#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-y-t-swap-v-restored.cjs');
const reserve=require('./k1-y-t-swap-v-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0';
const markers=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}
function visibleOperation(r,stage,earlySource,earlyValue,incoming,displaced) {
  const es=r.traced.events.filter(e=>e.stage===stage);
  same(es.filter(e=>[0xE9,0xA3].includes(e.ip)),[],'no X1 save or request in '+stage);
  const reads=es.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw]),[[earlySource,earlyValue],['X',incoming]]);
  const push=checks.exactPush(r,stage,['X','Y','Z','T']);same(push.displaced,displaced);
  const late=es.filter(e=>e.ip===0xE7&&e.command>reads[1].command);
  same(late.length,1);repack.exactCopy(r,late[0],'X',incoming);
  for(const w of r.traced.writes.filter(x=>x.command>=es[0].command&&x.command<=es.at(-1).command&&x.before!==x.value)) {
    const i=w.command-push.command;
    assert.ok(w.chip===3&&w.nibble%3===1&&w.nibble<37&&
      ((i>=0&&i<4&&w.slot===['X','Y','Z','T'][i])||(w.command===late[0].command&&w.slot==='X')),
      'undeclared changed tetra in '+stage+': '+JSON.stringify(w));
  }
  return {read:reads[0].command,push,lateRead:reads[1].command,lateWrite:late[0].command};
}
function check(r) {
  assert.ok(!r.options.dropByEnter&&!r.options.stopAfterDrop);
  const prefix=reserve.check(r,'reserve/drop-t');
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const start=checks.boundary(r,'reserve/drop-t');
  const readQ=checks.boundary(r,'reserve/read-q');
  const duplicate=checks.boundary(r,'reserve/restore/blind-duplicate');
  const duplicateEnd=checks.boundary(r,'reserve/restore/push-marker-0');
  const end=checks.boundary(r,r.options.verifyExit?'post/manual':'done');
  const post=r.options.verifyExit?checks.boundary(r,'post/program').command:Infinity;
  checks.protectedFields({...r,traced:{...r.traced,
    events:r.traced.events.filter(e=>e.command<post),writes:r.traced.writes.filter(e=>e.command<post)}},
    [0],['U','V','W','Q']);
  assert.ok(r.traced.writes.filter(x=>x.command<post&&x.slot==='marker'&&x.nibble%3===1&&x.nibble<37)
    .every(x=>x.before===x.value),'true-marker numeric word remains intact, including transient writes');
  assert.ok(r.traced.writes.filter(x=>x.command>=post&&
    ((x.nibble%3===0&&x.nibble<36)||(Object.hasOwn(r.before,x.slot)&&x.nibble%3===1)||
      [36,37,39,40].includes(x.nibble))).every(x=>x.before===x.value),
    'program execution leaves all stored numeric words and service fields unchanged');
  const drop=visibleOperation(r,'reserve/drop-t','W',u,w,m);
  const load=r.traced.events.find(e=>e.stage==='reserve/drop-t'&&e.ip===0xD6);
  same(load.slot,'U');same(raw(load.m,0),w);
  same(visible(readQ),[q,w,u,v,'14'+q.slice(2)]);same(markers(readQ),['marker']);
  const last=visibleOperation(r,'reserve/read-q','X1',q,q,'14'+q.slice(2));
  same(visible(duplicate),[q,q,w,u,v]);same(markers(duplicate),['marker']);
  const dupEvents=r.traced.events.filter(e=>e.stage==='reserve/restore/blind-duplicate');
  const firsts=dupEvents.filter(e=>e.ip===0xE7&&e.nextIp===0xA8);
  same(firsts.length,3);const dupPushes=firsts.map(first=>checks.exactPush({...r,
    traced:{...r.traced,events:r.traced.events.filter(e=>e.command>=first.command)}},
    'reserve/restore/blind-duplicate',['X','Y','Z','T']));
  same(dupPushes.map(x=>x.displaced),[v,u,w]);
  const dupLate=dupEvents.filter(e=>e.ip===0xE7&&e.nextIp===0x47);
  same(dupLate.length,3);dupLate.forEach(e=>repack.exactCopy(r,e,'X',q));
  same(visible(duplicateEnd),[q,q,q,q,q]);
  same(snapshotFromRing(duplicateEnd.ring).words,snapshotFromRing(start.ring).words,
    'RCL0, LastX and duplicates do not modify the stored bank');
  const restore=checks.exactPush(r,'reserve/restore/push',['T','U','V','W']);
  same(restore.displaced,u);
  const beforeRestore=ringAt(r,restore.command);
  same(raw(beforeRestore.T),q);same(raw(beforeRestore.V),u);same(raw(beforeRestore.W),u);
  const allowedMs=new Set([restore.command+1,restore.command+2,restore.command+3]);
  for(const wr of r.traced.writes.filter(x=>x.command>=start.command&&x.command<post&&x.before!==x.value)) {
    if(wr.nibble%3===0&&wr.nibble<36)assert.fail('ordinary register changed during closure');
    if(Object.hasOwn(r.before,wr.slot)&&wr.nibble%3===1)
      assert.ok(wr.chip===3&&allowedMs.has(wr.command)&&['U','V','W'].includes(wr.slot)&&wr.nibble<37,
        'undeclared Ms mutation during closure: '+JSON.stringify(wr));
  }
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+q,V:r.before.V,
    W:r.before.W.slice(0,2)+u,Q:r.before.Q.slice(0,2)+p});
  same(['U','V','W','Q'].map(n=>raw(end.ring[n])),[q,v,u,p]);same(markers(end),['marker']);
  const mapping=Array.from({length:23},(_,i)=>i);
  for(const [dst,src] of [[0,17],[15,18],[17,15],[18,0]])mapping[dst]=src;
  const oracle=analyzeTrace({beforeEvent:r.traced.events.find(e=>e.ring),afterEvent:end,
    writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  if(r.options.verifyExit) {
    same(r.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(r,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(r,'post/program').ring.X),'000000000000');
    const final=checks.boundary(r,'done');same(raw(final.ring.X),'000050000000');
    same(snapshotFromRing(final.ring).words,snapshotFromRing(end.ring).words);same(markers(final),['marker']);
  }
  return {prefix,boundaries:rows.length,dropT:drop,readQ:last,duplicates:dupPushes,restore,
    all23BackInStoredWords:true,allExtraMarkersRemoved:true,mapping,cycles:oracle.data.cycles,
    other14OrdinaryUpper4ProgramAndServicesHeld:true,workingExitTested:!!r.options.verifyExit,
    repeatabilityProved:false,numericDomainProved:false,fullK1:false};
}
function negativeEnter(r) {
  same(r.options.dropByEnter,true);same(r.options.stopAfterDrop,true);
  const prefix=reserve.check(r,'reserve/drop-t');
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  const at=checks.boundary(r,'reserve/drop-t'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='reserve/drop-t');
  const u=r.before.U.slice(2),p=r.beforeRegisters[0],a=r.before.P7.slice(2),b=r.before.P8.slice(2);
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['U',0x9E]]);
  same(es.filter(e=>e.ip===0xEE).map(e=>[e.slot,e.raw]),[['X',u],['X',u]]);
  const push=checks.exactPush(r,'reserve/drop-t',['W','Q','P7','P8']);same(push.displaced,b);
  const late=es.find(e=>e.ip===0xE7&&e.nextIp===0x47);repack.exactCopy(r,late,'W',u);
  same(es.filter(e=>[0xE9,0xA3].includes(e.ip)),[]);
  for(const x of r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.before!==w.value)) {
    const i=x.command-push.command;
    assert.ok(x.chip===3&&i>=0&&i<4&&x.slot===['W','Q','P7','P8'][i]&&x.nibble%3===1&&x.nibble<37,
      'undeclared changed tetra in rejected ENTER: '+JSON.stringify(x));
  }
  const expected=structuredClone(at.ring);
  for(const [n,value] of Object.entries({W:u,Q:u,P7:p,P8:a}))
    [...value].reverse().forEach((x,j)=>{expected[n][1+3*j]=parseInt(x,16);});
  same(end.ring,expected,'complete rejected ENTER changes only the upper-shifted push');
  same(repack.boundaryLosses(r).filter(e=>e.missing.length).map(e=>[e.stage,e.missing]),[['done',[b]]]);
  return {prefix,rejected:'ENTER instead of RCL0',push,lateCopy:late.command,
    lostFromStoredAndVisible:'old P8',notGeneralImpossibility:true};
}
if(require.main===module) {
  const negative=!!process.env.K1_SWAP_RESTORED_NEGATIVE;
  const o={...probe.defaults,verifyExit:!negative,...JSON.parse(process.env.K1_SWAP_RESTORED_OPTIONS||'{}'),
    ...(negative?{dropByEnter:true,stopAfterDrop:true}:{})};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS '+(negative?'negative ENTER':'restored reserve')+':',
    JSON.stringify((negative?negativeEnter:check)(r)));
  if(process.env.K1_SWAP_RESTORED_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check,negativeEnter};
