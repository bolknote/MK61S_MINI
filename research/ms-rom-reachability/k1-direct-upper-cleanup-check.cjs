#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-direct-upper-cleanup-probe.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b)=>assert.deepEqual(a,b),z='000000000000';
function lastx(r) {
  // Exact counterexample only: LastX is not a safe cleanup for this bridge.
  same(r.options.phaseOffset,1);same(r.options.incoming,'201');
  same(r.options.values,['811','822','833','844']);same(r.options.cleanup,[['F','В↑']]);
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const pre=checks.boundary(r,'cleanup-0'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='cleanup-0');
  const p=r.beforeRegisters[0],[v,w,q,a]=['V','W','Q','P7'].map(n=>r.before[n].slice(2));
  same(es.filter(e=>e.ip===0xEE).map(e=>[e.slot,raw(e.m),e.sp[0]]),[['W',p,0xF0],['Q',a,0xE3]]);
  const source=es.find(e=>e.ip===0xEE);
  same([source.s1,...[23,26,29].map(i=>source.r[i])],[14,0,0,0]);
  same(source.sp,[0xF0,0x8E,0x9A]);
  const push=checks.exactPush(r,'cleanup-0',['X','Y','Z','T']);same(push.displaced,w);
  const copied=ringAt(r,push.command+4);
  same(['X','Y','Z','T'].map(n=>raw(copied[n])),[p,q,z,v]);
  const formatter=es.find(e=>e.ip===0xE7&&e.nextIp===0x47);assert.ok(formatter);
  same([formatter.slot,raw(formatter.m),raw(formatter.r,0)],['X',p,a]);
  const expected=ringAt(r,formatter.command);
  for(let j=0;j<12;j++)expected.X[1+3*j]=formatter.r[3*j];
  same(ringAt(r,formatter.command+1),expected,'late formatting writes exactly X');
  same(['X1','X','Y','Z','T'].map(n=>raw(end.ring[n])),[q,a,q,z,v]);
  same(snapshotFromRing(end.ring).words,snapshotFromRing(pre.ring).words,'all 23 stored output words unchanged by LastX');
  const originals=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  same(originals.filter(n=>!live.includes(n)),[w]);
  return {rejected:'LastX after direct upper entry',phase:1,
    visiblePush:push.command,lostOriginalW:w,lateOverwrite:formatter.command,
    safeCleanup:false,fullK1:false};
}
if(require.main===module) {
  const r=probe.run({phaseOffset:1,cleanup:[['F','В↑']]});
  console.log('PASS rejected LastX cleanup:',JSON.stringify(lastx(r)));
  if(process.env.K1_DIRECT_CLEANUP_UNOBSERVED)console.log('PASS observer-free negative:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={lastx};
