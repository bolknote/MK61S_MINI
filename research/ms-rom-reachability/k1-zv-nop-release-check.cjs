#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zv-nop-release.cjs');
const release=require('./k1-zv-clear-check.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const zw=require('./k1-zw-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=assert.deepEqual;
function check(r) {
  same(r.options.deepTail,probe.defaults.deepTail);same(r.options.deepTailPhases,probe.defaults.deepTailPhases);
  same(r.options.afterW??[],[]);
  const prefix=release.entryPrefix(r,'deep/tail-2');
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const stage='deep/tail-2',es=r.traced.events.filter(e=>e.stage===stage),start=checks.boundary(r,stage),end=checks.boundary(r,'done');
  const gates=es.filter(e=>e.ip===0x9C),reads=es.filter(e=>e.ip===0xEE),writes=es.filter(e=>e.ip===0xE7);
  same(gates.map(e=>[e.slot,e.nextIp]),[['control',0x9E],['T',0x9E]]);
  same([gates[0].r[23],gates[0].r[26],gates[0].r[29]],[0,0,4]);
  const a=r.before.P7.slice(2);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['V','9990FFFFFFF0',0xAB],['X',a,0xE3]]);
  same(es.filter(e=>[0xE9,0xA3,0xA8,0xD4,0xD6].includes(e.ip)),[]);same(writes.length,1);
  const write=writes[0];repack.exactCopy(r,write,'V',a);
  zw.formatter(r,stage,reads[1],write,'V',['marker','Z','V']);
  const ww=r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command);
  same(ww.map(w=>[w.command,w.chip,w.slot,w.nibble]),Array.from({length:12},(_,i)=>[write.command,3,'V',1+3*i]));
  const expected=structuredClone(start.ring);deep.word(expected,'V',a);same(end.ring,expected);
  release.endpoint(r,end,'P7');const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  return {prefix,boundaries:rows.length,gates:gates.map(e=>[e.command,e.slot]),reads:reads.map(e=>[e.command,e.slot]),
    release:write.command,only12PrimaryWrites:true,wholeFrameWaitsOnly:true,all23Live:true,
    upperAInV:true,vOnlyInT:true,extraMarkers:['Z'],workingExit:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_ZV_NOP_OPTIONS||'{}')};
  console.log('PASS surface:',JSON.stringify(deep.surface(o,probe.finish)));
  if(!process.env.K1_ZV_NOP_SKIP_FRAME)console.log('PASS frames:',JSON.stringify(release.frameCheck(probe.run(o),'P7')));
  const r=probe.traced(o);console.log('PASS native:',JSON.stringify(check(r)));
  if(process.env.K1_ZV_NOP_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check};
