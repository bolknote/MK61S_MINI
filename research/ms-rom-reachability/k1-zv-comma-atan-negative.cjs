#!/usr/bin/env node
'use strict';
// A slower unary operation is not enough: arctg acknowledges the wrong
// marker, damages the sole T reserve and leaves its original request live.
const assert=require('node:assert/strict');
const probe=require('./k1-zv-comma-closed.cjs');
const transfer=require('./k1-zv-comma-transfer-check.cjs');
const closed=require('./k1-zv-comma-closed-check.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=assert.deepEqual,negative='002912500000',result='000915627965';
const copy=(c,chip,n,v)=>[...v].reverse().map((x,j)=>[c,chip,n,1+3*j,parseInt(x,16)]);
const key=w=>[w.command,w.chip,w.slot,w.nibble,w.value];
const ordered=xs=>xs.toSorted((a,b)=>a[0]-b[0]||a[1]-b[1]||a[3]-b[3]);
const options={...probe.defaults,fixtureRegisters:{8:'125'},
  afterTransfer:[['/-/'],['F','6']],afterTransferPhases:[0,1]};
function check(r) {
  same(r.options.afterTransfer,options.afterTransfer);same(r.options.afterTransferPhases,options.afterTransferPhases);
  const prefix=transfer.check(prefixView(r,'comma/tail-0',{afterTransfer:[],afterTransferPhases:[]}));
  closed.sign(r,{register:'002012500000',negative});
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);same(r.beforeProgram,r.afterProgram);
  const at=checks.boundary(r,'comma/tail-1'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='comma/tail-1');
  const ww=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['T',0x9E],['T',0x9E]]);
  same(es.filter(e=>e.ip===0xEE).map(e=>[e.slot,e.raw,e.nextIp]),[['X',negative,0xA1],['X',negative,0xE3]]);
  const one=ip=>{const xs=es.filter(e=>e.ip===ip);same(xs.length,1);return xs[0];};
  const save=one(0xE9),req=one(0xA3),late=one(0xE7);
  same(req.slot,'control');repack.exactCopy(r,save,'U',negative);repack.exactCopy(r,late,'X',negative);
  const secondary=ww.filter(w=>w.chip===4),acks=secondary.filter(w=>w.ip===0x27),outs=secondary.filter(w=>w.ip===0x2A);
  same(secondary.length,acks.length+outs.length);same(acks.length,11);same(outs.length,12*acks.length);
  same(acks.map(w=>[w.command-req.command,w.slot,w.nibble,w.value]),
    acks.map((_,i)=>[456+465*i,'T',31,15]));
  same(outs.map(key),acks.flatMap(w=>copy(w.command+2,4,'V',result)));
  const firstAck=acks[0],beforeAck=ringAt(r,firstAck.command),afterAck=structuredClone(beforeAck);
  same(raw(beforeAck.T),r.before.V.slice(2));afterAck.T[31]=15;
  same(ringAt(r,firstAck.command+1),afterAck,'the first misplaced ACK alone corrupts v');
  const hv=[2,11,1],expected=structuredClone(at.ring);
  deep.word(expected,'U',negative);deep.word(expected,'V',result);expected.T[31]=15;
  [28,31,34].forEach((n,j)=>{expected.control[n]=hv[j];});
  same(end.ring,expected,'all 630 tetras, including unacknowledged control request');
  same(ordered(ww.map(key)),ordered([...copy(save.command,3,'U',negative),
    ...[28,31,34].map((n,j)=>[req.command,3,'control',n,hv[j]]),...copy(late.command,3,'X',negative),
    ...acks.map(key),...outs.map(key)]));
  const losses=repack.boundaryLosses(r).filter(e=>e.missing.length);
  same(losses.map(e=>[e.stage,e.missing]),[['done',[r.before.V.slice(2)]]]);
  return {prefix,primaryRequest:req.command,primaryRequestSafelyInControl:true,
    firstWrongAck:firstAck.command,firstResult:firstAck.command+2,resultSlot:'V',
    observedRepetitions:acks.length,periodCommands:465,pendingRequestAtRecordedEnd:true,
    wholeVAbsentFromTrackedNumericWords:true,fullStateCollisionProved:false,validExit:false};
}
if(require.main===module) {
  console.log('PASS surface:',JSON.stringify(deep.surface(options,probe.finish)));
  const r=probe.traced(options);console.log('PASS arctg counterexample:',JSON.stringify(check(r)));
  if(process.env.K1_COMMA_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={options,check};
