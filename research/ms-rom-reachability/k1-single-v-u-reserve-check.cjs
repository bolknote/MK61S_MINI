#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-single-v-u-reserve.cjs');
const single=require('./k1-single-v-entry-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0',inv='00008FFFFFFF';
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const markers=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const setWord=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});

function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}

function check(r,endStage='done') {
  if(endStage!=='done')r=prefixView(r,endStage);
  same(r.options.reserveLeadPhase,1);
  const prefix=single.check(prefixView(r,'after-clone-phase',{afterClone:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q']);
  assert.ok(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.nibble<37)
    .every(w=>w.before===w.value),'true numeric marker held including transient writes');
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const at=checks.boundary(r,'after-clone-0'),end=checks.boundary(r,'done');
  same(visible(at),[inv,u,q,m,m]);same(visible(end),[inv,v,u,q,m]);same(markers(end),['T','V','marker']);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+m,
    W:r.before.W.slice(0,2)+a,Q:r.before.Q.slice(0,2)+p});
  const es=r.traced.events.filter(e=>e.stage==='after-clone-0');
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);
  same(es.filter(e=>[0xE9,0xA3].includes(e.ip)),[],'no new request or X1 overwrite');
  const reads=es.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['U',v,0xF0],['P7',a,0xE3]]);
  const push=checks.exactPush(r,'after-clone-0',['X','Y','Z','T']);same(push.displaced,m);
  const late=es.filter(e=>e.ip===0xE7&&e.command>reads[1].command);
  same(late.length,1);repack.exactCopy(r,late[0],'W',a);
  const ips='9C 9E 8C 91 92 93 94 95 98 9A 93 94 95 98 9A 8D 4F FF E5 E5 E6 EE F0 E0 A7 E5 E5 E5 E5 E5 E6 E8 E7 A8 A8 A8 A9 E1 91 92 93 94 95 98 9A 93 94 95 98 9A E2 E5 E5 E6 ED EE'.split(' ').map(s=>parseInt(s,16));
  const first=es.find(e=>e.ip===0x9C).command;
  same(es.filter(e=>e.command>=first&&e.command<first+ips.length).map(e=>[e.ip,e.slot]),
    ips.map((ip,i)=>[ip,slots[(1+i)%15]]),'connected native LastX path through both EE readers');
  const allowed=new Set([push.command,push.command+1,push.command+2,push.command+3,late[0].command]);
  same(r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.before!==w.value)
    .filter(w=>w.chip!==3||!allowed.has(w.command)),[],'no undeclared changed tetras in reserve');
  const expected=structuredClone(at.ring);
  for(const [n,value] of Object.entries({X:v,Y:u,Z:q,W:a}))setWord(expected,n,value);
  same(end.ring,expected,'whole 630-tetra reserve endpoint');
  const rows=repack.boundaryLosses(r);same(rows.filter(x=>x.missing.length),[]);
  return {prefix,boundaries:rows.length,readU:reads[0].command,push,readUpper:reads[1].command,lateCopyW:late[0].command,
    all23LiveAtEveryBoundary:true,oldVNowInXAndU:true,uOnlyInY:true,qOnlyInZ:true,
    upper4Other14OrdinaryProgramAndServicesHeld:true,remainingMarkers:['T','V'],
    normalExit:false,newUpperPair:false,fullK1:false};
}

function negativeRotate(r) {
  same(r.options.afterReserve,[['F',',']]);
  const prefix=check(r,'u-reserve/tail-0');
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  const [u,v,w,q,a,b]=['U','V','W','Q','P7','P8'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const at=checks.boundary(r,'u-reserve/tail-0'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='u-reserve/tail-0');
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E],['control',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['W',a,0xA1],['P7',a,0xE3]]);
  const save=es.find(e=>e.ip===0xE9);repack.exactCopy(r,save,'X1',a);
  const req=es.find(e=>e.ip===0xA3);same(req.slot,'U');
  const expectedReq=ringAt(r,req.command);setWord(expectedReq,'U','25'+a[2]+v.slice(3));
  same(ringAt(r,req.command+1),expectedReq,'only three U request header tetras change');
  same(raw(ringAt(r,req.command+1).X),v,'U overwrite is safe because full v remains in X');
  const secondary=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.chip===4);
  const ack=secondary.filter(w=>w.ip===0x27);same(ack.map(w=>[w.slot,w.nibble,w.value]),[['U',31,15],['U',31,15]]);
  const out=secondary.filter(w=>w.ip!==0x27),first=out[0].command;
  same(out.map(w=>[w.command-first,w.slot,w.nibble,w.ip]),['W','Q','P7','P8'].flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i,n,1+3*j,i===3?0x2A:0x3A])));
  const beforeOutput=ringAt(r,first),rotated=structuredClone(beforeOutput);
  for(const [dest,source] of [['W','Q'],['Q','P7'],['P7','P8'],['P8','W']])setWord(rotated,dest,raw(beforeOutput[source]));
  same(ringAt(r,first+4),rotated,'exact secondary W/Q/P7/P8 rotation, all 630 tetras');
  const late=es.find(e=>e.ip===0xE7);same(raw(late.m),p);repack.exactCopy(r,late,'W',a);
  assert.ok(reads[1].command<first&&late.command>first+3,'late buffer reads old a before the rotation');
  const beforeLate=ringAt(r,late.command);
  same(['X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'].filter(n=>raw(beforeLate[n])===p),['W']);
  const expected=structuredClone(at.ring);
  for(const [n,value] of Object.entries({X1:a,U:'2F'+a[2]+v.slice(3),W:a,Q:a,P7:b,P8:a}))setWord(expected,n,value);
  same(end.ring,expected,'exact failing endpoint');
  const allowed=new Set([
    ...[save.command,req.command,late.command].map(c=>'3:'+c),
    ...[...ack.map(w=>w.command),first,first+1,first+2,first+3].map(c=>'4:'+c),
  ]);
  same(r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.before!==w.value
    &&!allowed.has(w.chip+':'+w.command)),[],'no undeclared per-chip changed tetras');
  same(repack.boundaryLosses(r).filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),[['done',[p]]]);
  return {prefix,request:req.command,rotation:first,lateRead:reads[1].command,destructiveLateWrite:late.command,
    UReserveWorks:true,lostOnlyOriginalP0:p,noSecondRotateBecauseActualURequestAcknowledged:true,
    notGeneralImpossibility:true,fullK1:false};
}

if(require.main===module) {
  const negative=!!process.env.K1_U_RESERVE_NEGATIVE;
  const o={...probe.defaults,...JSON.parse(process.env.K1_U_RESERVE_OPTIONS||'{}'),...(negative?{afterReserve:[['F',',']]}:{})};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS '+(negative?'rejected upper rotation':'U reserve')+':',JSON.stringify((negative?negativeRotate:check)(r)));
  if(process.env.K1_U_RESERVE_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check,negativeRotate};
