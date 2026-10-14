#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-vw-upper-read.cjs');
const deep=require('./k1-repack-deep-clone-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {pair}=require('./k1-first-upper-bridge-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0',one='000010000000';
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
function read(r,endStage='done',lateTarget='X') {
  const prefix=deep.check(r,'after-clone-0'),end=checks.boundary(r,endStage);
  const [u,v,w,q,a,b]=['U','V','W','Q','P7','P8'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const es=r.traced.events.filter(e=>e.stage==='after-clone-0');
  const source=es.find(e=>e.ip===0xEE);
  same([source.slot,source.raw,source.nextIp],['V',m,0xF0]);
  same([source.s1,source.r[23],source.r[26],source.r[29],...source.sp],
    [14,0,0,0,0xF0,0x8E,0x9A]);
  const push=checks.exactPush(r,'after-clone-0',['X','Y','Z','T']);same(push.displaced,m);
  const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
  same([lateRead.slot,lateRead.raw],['P7',a]);
  const late=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);
  repack.exactCopy(r,late,lateTarget,a);
  same(raw(late.m),lateTarget==='X'?m:lateTarget==='T'?q:b);
  const at=checks.boundary(r,'after-clone-0').command;
  assert.ok(r.traced.writes.filter(e=>e.command>=at&&e.command<end.command&&
    e.slot==='X1'&&e.nibble%3===1).every(e=>e.before===e.value),
    'the complete read leaves X1 unchanged, including transient writes');
  assert.ok(r.traced.writes.filter(e=>e.command>=at&&e.command<end.command&&
    Object.hasOwn(r.before,e.slot)&&e.nibble%3===1&&e.slot!==lateTarget)
    .every(e=>e.before===e.value),'all other Ms words held during the read');
  same(visible(end),['00008FFFFFFF',lateTarget==='X'?a:m,one,u,lateTarget==='T'?a:q]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),
    lateTarget==='X'?['V','W','marker']:['V','W','X','marker']);
  const want={U:v,V:m,W:m,Q:p};
  for(const n of ['P7','P8','P9','P10'])want[n]=n===lateTarget?a:r.before[n].slice(2);
  same(Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(end.ring[n])])),want);
  same(raw(end.ring.U,0),w);
  return {prefix,source:source.command,push,lateRead:lateRead.command,
    lateWrite:late.command,lateTarget};
}
function check(r,which='read') {
  const negative=which==='short'||which==='full',swap=which==='swap';
  same(r.options.afterRead??[],swap?[['↔']]:[]);
  checks.protectedFields(r,[0],['U','V','W','Q',...(swap||which==='full'?['P7','P8']:[])]);
  const target=which==='short'?'T':which==='full'?'P8':'X';
  const path=read(r,swap?'after-read-0':'done',target),rows=repack.boundaryLosses(r);
  const a=r.before.P7.slice(2),b=r.before.P8.slice(2),q=r.before.Q.slice(2);
  const bad=rows.filter(e=>e.missing.length);
  if(negative) {
    same(bad.map(e=>[e.stage,e.missing]),[['done',[which==='short'?q:b]]]);
    return {rejected:which==='short'?'normalization class 7':'normalization class 0',
      path,lost:which==='short'?'original lower Q':'original upper P8',notGeneralImpossibility:true};
  }
  same(bad,[]);
  let exchange;
  if(swap) {
    const es=r.traced.events.filter(e=>e.stage==='after-read-0');
    const source=es.find(e=>e.ip===0xEE&&e.nextIp===0xA1);same([source.slot,source.raw],['P7',a]);
    repack.exactCopy(r,es.find(e=>e.ip===0xE9),'X1',a);
    const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);same([lateRead.slot,lateRead.raw],['P7',a]);
    const late=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);repack.exactCopy(r,late,'X',a);
    exchange=pair(r,'after-read-0','P7','P8');
    const end=checks.boundary(r,'done');
    same(visible(end),[a,a,one,r.before.U.slice(2),q]);
    const before=checks.boundary(r,'after-read-0');
    const expected=Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(before.ring[n])]));
    expected.P7=b;expected.P8=a;expected.W='1F'+a[2]+m.slice(3);
    same(Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(end.ring[n])])),expected);
    same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['V','W','marker']);
  }
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:r.before.W.slice(2)));
  return {boundaries:rows.length,all23HeldAtEveryBoundary:true,path,exchange,
    upperCopyInVisibleX:true,oldX1NotNeededForRead:true,workingExit:false,fullK1:false};
}
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,assumedSuccessfulAttempts:1,initialPhaseOffsetExcluded:true};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_VW_READ_OPTIONS||'{}'),which=process.env.K1_VW_READ_CASE??'read';
  assert.ok(['read','swap','short','full'].includes(which));
  if(which==='short')o.fullUpper=['-1E-99','9022','9033','9044'];
  if(which==='full')o.fullUpper=['1.2345678E42','9022','9033','9044'];
  if(which==='swap')o.afterRead=[['↔']];
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS '+which+':',JSON.stringify(check(r,which)));
  if(process.env.K1_VW_READ_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={read,check,surface};
