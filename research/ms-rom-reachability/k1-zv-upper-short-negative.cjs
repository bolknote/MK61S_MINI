#!/usr/bin/env node
'use strict';
// Same upper-transfer prefix, but a=402 has decimal formatter class 6.
// NOP writes P7 instead of V; the following late copy damages old P8.
// This is a whole-word preservation counterexample, not a state collision.
const assert=require('node:assert/strict');
const probe=require('./k1-zv-upper-closed.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=assert.deepEqual,m='9990FFFFFFF0';
const options={...probe.defaults,fullUpper:['402','9022','9033','9044'],
  afterW:[['П→X','8']],afterWPhases:[0],verifyExit:false};
function exactWrites(r,from,to,groups) {
  const at=checks.boundary(r,from),end=checks.boundary(r,to);
  same(r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command).map(w=>[w.command,w.chip,w.slot,w.nibble]),
    groups.flatMap(([c,n])=>Array.from({length:12},(_,j)=>[c,3,n,1+3*j])));
}
function check(r) {
  same(r.options.fullUpper,options.fullUpper);same(r.options.afterW,options.afterW);
  const prefix=deep.check(prefixView(r,'deep/tail-1',{deepTail:[['K','0']],deepTailPhases:[1]}));
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  const a=r.before.P7.slice(2),u=r.before.U.slice(2),v=r.before.V.slice(2),b=r.before.P8.slice(2);
  const at=s=>checks.boundary(r,s),es=s=>r.traced.events.filter(e=>e.stage===s);
  const enter=es('deep/tail-1'),er=enter.filter(e=>e.ip===0xEE),el=enter.filter(e=>e.ip===0xE7&&e.nextIp===0x47);
  same(enter.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);
  same(er.map(e=>[e.slot,e.raw,e.nextIp]),[['U',u,0xE0],['P7',a,0xE3]]);same(el.length,1);
  const ep=checks.exactPush(r,'deep/tail-1',['X','Y','Z','T']);same(ep.displaced,m);repack.exactCopy(r,el[0],'X',a);
  exactWrites(r,'deep/tail-1','deep/tail-2',[...['X','Y','Z','T'].map((n,i)=>[ep.command+i,n]),[el[0].command,'X']]);
  const expectedEnter=structuredClone(at('deep/tail-1').ring);
  for(const [n,value] of [['X',a],['Y',u],['Z',m],['T',v]])deep.word(expectedEnter,n,value);
  same(at('deep/tail-2').ring,expectedEnter);
  const ns=es('deep/tail-2'),nr=ns.filter(e=>e.ip===0xEE),nl=ns.filter(e=>e.ip===0xE7);
  same(nr.map(e=>[e.slot,e.raw,e.nextIp]),[['V',m,0xAB],['X',a,0xE3]]);same(nl.length,1);
  repack.exactCopy(r,nl[0],'P7',a);exactWrites(r,'deep/tail-2','w/tail-0',[[nl[0].command,'P7']]);
  same(at('w/tail-0').ring,expectedEnter,'NOP is idempotent in P7 and does not remove V');
  const re=es('w/tail-0'),rr=re.filter(e=>e.ip===0xEE),rl=re.filter(e=>e.ip===0xE7&&e.nextIp===0x47);
  same(rr.map(e=>[e.slot,e.raw,e.nextIp]),[['V',m,0xAB],['X',a,0xE3]]);same(rl.length,1);
  const d6=re.filter(e=>e.ip===0xD6);same(d6.length,1);same(d6[0].slot,'marker');
  same(raw(ringAt(r,d6[0].command).marker,0),r.beforeRegisters[8]);
  const rp=checks.exactPush(r,'w/tail-0',['V','W','Q','P7']);same(rp.displaced,a);
  repack.exactCopy(r,rl[0],'P8',a);
  exactWrites(r,'w/tail-0','done',[...['V','W','Q','P7'].map((n,i)=>[rp.command+i,n]),[rl[0].command,'P8']]);
  const expected=structuredClone(expectedEnter);deep.word(expected,'V',r.beforeRegisters[8]);
  for(const [dst,src] of [['W','V'],['Q','W'],['P7','Q']])deep.word(expected,dst,raw(expectedEnter[src]));
  deep.word(expected,'P8',a);same(at('done').ring,expected);
  same(repack.boundaryLosses(prefixView(r,'w/tail-0')).filter(e=>e.missing.length),[]);
  const end=at('done'),live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  same(original.filter(value=>!live.includes(value)),[b]);
  return {prefix,enterLateX:el[0].command,nopLateP7:nl[0].command,hiddenPush:rp.command,
    destructiveLateP8:rl[0].command,missingWholeWord:'old P8',fullStateCollisionProved:false,
    arbitraryNumbersSafe:false,fullK1ImpossibilityProved:false};
}
if(require.main===module) {
  const r=probe.traced(options);console.log('PASS short-a negative:',JSON.stringify(check(r)));
  if(process.env.K1_ZV_SHORT_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={options,check};
