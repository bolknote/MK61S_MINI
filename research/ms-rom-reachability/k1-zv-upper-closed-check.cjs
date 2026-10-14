#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zv-upper-closed.cjs');
const close=require('./k1-zv-nop-closed-check.cjs');
const nop=require('./k1-zv-nop-release-check.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const zw=require('./k1-zw-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=assert.deepEqual,zero='000000000000';
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const mapping=Array.from({length:23},(_,i)=>i);
for(const [dst,src] of [[0,17],[17,19],[19,0]])mapping[dst]=src;
function frameCheck(r) {
  const original=snapshotFromRing(r.initial),at=s=>{const e=r.rows.find(x=>x.stage===s);assert.ok(e,s);return e;};
  same(new Set(original.words).size,23);same(r.rows.filter(x=>x.missing.length),[]);
  for(const e of r.rows) {
    const s=snapshotFromRing(e.ring);same(s.program,original.program);same(s.services,original.services);
    same(s.words.slice(1,15),original.words.slice(1,15));same(s.words.slice(20),original.words.slice(20));
    same(e.values.marker,'000FFFFFFFFF');
  }
  for(const stage of [r.options.verifyExit?'post/manual':'immediate','done']) {
    const e=at(stage);same(snapshotFromRing(e.ring).words,mapping.map(i=>original.words[i]));same(marks(e),['marker']);
  }
  if(r.options.verifyExit) {
    same(at('post/zero').values.X,'000050000000');same(at('post/program').values.X,zero);
    same(at('done').values.X,'000050000000');
  }
  return {boundaries:r.rows.length,all23Live:true,all23StoredAtExit:true,upper3Fixed:true,
    allExtraMarkersRemoved:true,workingExitTested:!!r.options.verifyExit,fullK1:false};
}
function upperPush(r) {
  const stage='w/tail-0',at=checks.boundary(r,stage),end=checks.boundary(r,'w/tail-1');
  const es=r.traced.events.filter(e=>e.stage===stage),a=r.before.P7.slice(2);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  const gates=es.filter(e=>e.ip===0x9C);same(gates.map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE),d6=es.filter(e=>e.ip===0xD6),late=es.filter(e=>e.ip===0xE7&&e.nextIp===0x47);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['V',a,0xAB],['X',a,0xE3]]);
  same(d6.length,1);same(d6[0].slot,'marker');same(raw(ringAt(r,d6[0].command).marker,0),r.beforeRegisters[8]);
  same(late.length,1);same(es.filter(e=>[0xE9,0xA3,0xD4].includes(e.ip)),[]);
  const shifted=checks.exactPush(r,stage,['V','W','Q','P7']);same(shifted.displaced,a);
  const pushed=ringAt(r,shifted.command+4);same(raw(pushed.V),r.beforeRegisters[8]);
  same(raw(pushed.W),a);same(raw(pushed.Q),raw(at.ring.W));same(raw(pushed.P7),raw(at.ring.Q));
  repack.exactCopy(r,late[0],'V',a);zw.formatter(r,stage,reads[1],late[0],'V',['marker','Z']);
  const ww=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
  same(ww.map(w=>[w.command,w.chip,w.slot,w.nibble]),
    [...['V','W','Q','P7'].map((n,i)=>[shifted.command+i,n]),[late[0].command,'V']]
      .flatMap(([c,n])=>Array.from({length:12},(_,j)=>[c,3,n,1+3*j])));
  const expected=structuredClone(at.ring);
  for(const [dst,src] of [['W','V'],['Q','W'],['P7','Q']])deep.word(expected,dst,raw(at.ring[src]));
  same(end.ring,expected,'all 630 upper-transfer endpoint tetras');same(marks(end),['Z','marker']);
  return {accepted:gates[0].command,earlyRead:reads[0].command,ordinary8:d6[0].command,
    push:shifted.command,lateRead:reads[1].command,lateWrite:late[0].command,
    only48PushAnd12LateTetras:true,noNewHiddenMarker:true};
}
function suffixView(r) {
  // Passive journal relabelling only, to reuse all exact closing-operation
  // checks. The inserted upper push is audited separately above.
  return {...r,traced:{...r.traced,events:r.traced.events.map(e=>{
    const m=/^w\/tail(-phase)?-(\d+)$/.exec(e.stage);
    return m?{...e,stage:Number(m[2])===0?'upper'+e.stage:'w/tail'+(m[1]??'')+'-'+(Number(m[2])-1)}:e;
  })}};
}
function check(full) {
  const r=full.options.verifyExit?prefixView(full,'post/manual'):full;
  same(r.options.afterW,probe.defaults.afterW);same(r.options.afterWPhases,probe.defaults.afterWPhases);
  const prefix=nop.check(prefixView(r,'w/tail-0',{afterW:[],afterWPhases:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);same(full.afterProgram,full.beforeProgram);
  same(full.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const transfer=upperPush(r),s=suffixView(r);
  const operations=[close.max(s),close.subtract(s),close.push(s,2),close.push(s,3),close.push(s,4)];
  const initial=r.traced.events.find(e=>e.ring),end=checks.boundary(r,'done');
  const oracle=analyzeTrace({beforeEvent:initial,afterEvent:end,writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');same(marks(end),['marker']);
  const rows=repack.boundaryLosses(full);same(rows.filter(e=>e.missing.length),[]);
  if(full.options.verifyExit) {
    same(full.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(full,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(full,'post/program').ring.X),zero);
    const done=checks.boundary(full,'done');same(raw(done.ring.X),'000050000000');same(marks(done),['marker']);
    same(snapshotFromRing(done.ring).words,snapshotFromRing(end.ring).words);
    same(full.traced.writes.filter(w=>w.command>=end.command&&w.before!==w.value&&
      ((w.nibble%3===0&&w.nibble<36)||(Object.hasOwn(full.before,w.slot)&&w.nibble%3===1)||[36,37,39,40].includes(w.nibble))),[]);
  }
  return {prefix,transfer,boundaries:rows.length,operations,cycles:oracle.data.cycles,
    all23Live:true,all23StoredAtExit:true,upper3Other14OrdinaryProgramAndServicesHeld:true,
    allExtraMarkersRemoved:true,workingExitTested:!!full.options.verifyExit,
    longUpperTransferClosed:true,lastTwoMsChanged:false,repeatabilityProved:false,wholeNumericDomainProved:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,verifyExit:true,...JSON.parse(process.env.K1_ZV_UPPER_OPTIONS||'{}')};
  console.log('PASS surface:',JSON.stringify(deep.surface(o,probe.finish)));
  if(!process.env.K1_ZV_UPPER_SKIP_FRAME)console.log('PASS frames:',JSON.stringify(frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS native:',JSON.stringify(check(r)));
  if(process.env.K1_ZV_UPPER_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={mapping,frameCheck,upperPush,suffixView,check};
