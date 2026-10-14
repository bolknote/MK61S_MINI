#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-masked-add-zero-swap.cjs');
const add=require('./k1-u-reserve-masked-add-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {pair}=require('./k1-first-upper-bridge-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const word=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});
const zero='000000000000';
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();

function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}

function check(r,endStage='done') {
  if(endStage!=='done')r=prefixView(r,endStage);
  const negative=!!r.options.omitZeroGuard;
  const first=negative?'zero-swap/exchange':'zero-swap/clear';
  const prefix=add.check(r,false,first);
  const begin=checks.boundary(r,first),at=checks.boundary(r,'zero-swap/exchange'),end=checks.boundary(r,'done');
  const p=r.beforeRegisters[0],[v,w,a]=['V','W','P7'].map(n=>r.before[n].slice(2));
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.nibble<37&&w.before!==w.value),[]);
  const allowed=new Set();let clear;
  if(!negative) {
    const es=r.traced.events.filter(e=>e.stage==='zero-swap/clear');
    same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);
    const cs=es.filter(e=>e.ip===0xE7);same(cs.length,1);clear=cs[0];
    repack.exactCopy(r,clear,'X',zero);allowed.add('3:'+clear.command);
    const expected=structuredClone(begin.ring);word(expected,'X',zero);
    same(at.ring,expected,'Cx and the phase wait change only visible X, not hidden data');
  }
  const es=r.traced.events.filter(e=>e.stage==='zero-swap/exchange');
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]),'all-chip observations');
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E],['control',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE),visible=negative?v:zero;
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['W',p,0xA1],['X',visible,0xE3]]);
  const copies=es.filter(e=>e.ip===0xE9);same(copies.length,1);
  repack.exactCopy(r,copies[0],'X1',p);allowed.add('3:'+copies[0].command);
  const requests=es.filter(e=>e.ip===0xA3);same(requests.length,1);
  const req=requests[0];same(req.slot,'U');
  const expectedReq=ringAt(r,req.command);
  [28,31,34].forEach((n,i)=>{expectedReq.U[n]=[parseInt(p[2],16),4,1][i];});
  same(ringAt(r,req.command+1),expectedReq,'only three U request tetras change');
  same(r.traced.writes.filter(w=>w.command===req.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
    [28,31,34].map((n,i)=>[3,'U',n,[parseInt(p[2],16),4,1][i]]));
  allowed.add('3:'+req.command);
  const sw=pair(r,'zero-swap/exchange','W','Q');
  const out=ringAt(r,sw.command+2);
  same([raw(out.W),raw(out.Q)],[a,p],'the complete secondary swap succeeds even in the rejected variant');
  const secondary=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.chip===4);
  same(secondary.map(w=>[w.ip,w.slot,w.nibble]),[
    [0x27,'U',31],...[[0x4E,'W'],[0x2A,'Q']].flatMap(([ip,n])=>
      Array.from({length:12},(_,j)=>[ip,n,1+3*j]))]);
  same([secondary[0].before,secondary[0].value],[4,15]);
  for(const wr of secondary)allowed.add('4:'+wr.command);
  // Match the whole native secondary consumer, not just its endpoint.
  const start=es.find(e=>e.command>=req.command&&e.otherChips[4].ip===0x6E&&
    e.otherChips[4].slot==='T'&&e.command<sw.command);assert.ok(start);
  const route=[['6E','T'],['5E','U'],['50','V'],['52','W'],['53','Q'],['4F','P7'],
    ['41','P8'],['43','P9'],['4D','P10'],['60','marker'],
    ...['control','X1','X','Y','Z','T'].map(n=>['37',n]),
    ['27','U'],['61','V'],['4E','W'],['2A','Q'],['39','P7']];
  const native=es.filter(e=>e.command>=start.command&&e.command<start.command+route.length);
  same(native.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),route.map(([ip,n])=>[parseInt(ip,16),n]));
  same(native[0].otherChips[4].r[29],0);
  same([raw(native[3].otherChips[4].m),raw(native[4].otherChips[4].m)],[p,a]);
  const lates=es.filter(e=>e.ip===0xE7);same(lates.length,1);const late=lates[0];
  repack.exactCopy(r,late,negative?'W':'X',visible);allowed.add('3:'+late.command);
  assert.ok(sw.command+1<late.command,'the formatter executes after the completed secondary swap');
  if(negative)same(raw(late.m),a,'the late W write destroys the only remaining upper a');
  const expected=structuredClone(begin.ring);
  for(const [n,value] of Object.entries({X:visible,X1:p,W:negative?v:a,Q:p,
    U:'1F'+p[2]+raw(begin.ring.U).slice(3)}))word(expected,n,value);
  same(end.ring,expected,'full 630-tetra endpoint');same(marks(end),['T','marker']);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&w.before!==w.value
    &&!allowed.has(w.chip+':'+w.command)),[],'all changed tetras have declared owners');
  const rows=repack.boundaryLosses(r);
  same(rows.filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),negative?[['done',[a]]]:[]);
  return {prefix,boundaries:rows.length,zeroGuard:!negative,clear:clear?.command,read:reads[0].command,
    reserve:copies[0].command,request:req.command,consumer:start.command,swap:sw.command,
    lateRead:reads[1].command,lateWrite:late.command,lateTarget:late.slot,
    all23LiveAtEveryBoundary:!negative,upperAInW:!negative,originalPInQ:true,
    uOnlyInY:true,qOnlyInZ:true,remainingMarker:'T',normalExit:false,fullK1:false,
    ...(negative?{lostOriginalUpperA:a,notGeneralImpossibility:true}:{})};
}

function cleared(r) {
  same(r.options.afterZeroSwap,[['П→X','0']]);assert.ok(!r.options.omitZeroGuard);
  const prefix=check(r,'zero-swap/tail-0');
  const at=checks.boundary(r,'zero-swap/tail-0'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='zero-swap/tail-0');
  const [u,w,q,a]=['U','W','Q','P7'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const gates=es.filter(e=>e.ip===0x9C);same(gates.length,1);
  assert.ok(['control','U'].includes(gates[0].slot));same(gates[0].nextIp,0x9E);
  same(es.filter(e=>[0xE9,0xA3].includes(e.ip)),[],'RCL0 makes no X1 save or pending request');
  const reads=es.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw]),[[gates[0].slot==='control'?'W':'X',gates[0].slot==='control'?a:zero],['X',w]]);
  const loads=es.filter(e=>e.ip===0xD6);same(loads.length,1);const load=loads[0];
  same([load.slot,raw(load.m,0)],['U',w]);
  const afterLoad=es.find(e=>e.command===load.command+1);same([afterLoad.ip,afterLoad.slot],[0xA7,'V']);
  const push=checks.exactPush(r,'zero-swap/tail-0',['X','Y','Z','T']);same(push.displaced,'9990FFFFFFF0');
  const lates=es.filter(e=>e.ip===0xE7&&e.command>reads[1].command);same(lates.length,1);const late=lates[0];
  same(reads[1].nextIp,0xE3);repack.exactCopy(r,late,'X',w);
  const allowed=new Set([push.command,push.command+1,push.command+2,push.command+3,late.command]);
  same(r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.before!==w.value&&
    (w.chip!==3||!allowed.has(w.command))),[],'RCL0 has no other changed tetras');
  const expected=structuredClone(at.ring);
  for(const [n,value] of Object.entries({X:w,Y:zero,Z:u,T:q}))word(expected,n,value);
  same(end.ring,expected,'marker removal changes only the four visible stack words');same(marks(end),['marker']);
  same(['X1','W','Q'].map(n=>raw(end.ring[n])),[p,a,p]);
  const rows=repack.boundaryLosses(r);same(rows.filter(x=>x.missing.length),[]);
  return {prefix,boundaries:rows.length,acceptedAt:gates[0].slot,ordinaryRead:load.command,
    push,lateRead:reads[1].command,lateWrite:late.command,all23LiveAtEveryBoundary:true,
    allExtraMarkersRemoved:true,bankAndX1UnchangedByRecall:true,uOnlyInZ:true,qOnlyInT:true,
    UStillRequestHeader:true,all23BackInStoredWords:false,normalExitTested:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_ZERO_SWAP_OPTIONS||'{}'),
    ...(process.env.K1_ZERO_SWAP_CLEAR?{afterZeroSwap:[['П→X','0']]}:{}),
    ...(process.env.K1_ZERO_SWAP_NEGATIVE?{omitZeroGuard:true}:{})};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS '+(o.omitZeroGuard?'unguarded rejection':process.env.K1_ZERO_SWAP_CLEAR?'marker removed':'zero-guarded swap')+':',
    JSON.stringify((process.env.K1_ZERO_SWAP_CLEAR?cleared:check)(r)));
  if(process.env.K1_ZERO_SWAP_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check,cleared};
