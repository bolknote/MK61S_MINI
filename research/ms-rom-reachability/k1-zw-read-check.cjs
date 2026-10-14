#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zw-read.cjs');
const entry=require('./k1-zw-entry-check.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];

function check(r) {
  same(r.options.afterW,[['K','0']]);same(r.options.afterWPhases,[0]);
  const prefix=entry.check(prefixView(r,'w/tail-0',{afterW:[],afterWPhases:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const es=r.traced.events.filter(e=>e.stage==='w/tail-0'),start=checks.boundary(r,'w/tail-0'),end=checks.boundary(r,'done');
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  const gates=es.filter(e=>e.ip===0x9C),reads=es.filter(e=>e.ip===0xEE),late=es.filter(e=>e.ip===0xE7);
  same(gates.map(e=>[e.slot,e.nextIp]),[['T',0x9E],['control',0x9E]]);
  same([gates[0].r[23],gates[0].r[26],gates[0].r[29]],[0,0,4]);
  const a=r.before.P7.slice(2),b=r.before.P8.slice(2);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['X',a,0xAB],['P8',b,0xE3]]);same(late.length,1);
  deep.path(es,gates[0].command,'T',deep.ips('9C 9E 9F AA E5 E5 E5 E5 E5 E5 E6 ED EE AB AD A5 1F 14 D3 D5 9B 9B 9B 9B 9B 9C 9E 9F AA AC E2 E5 E5 E5 E6 ED EE'));
  repack.exactCopy(r,late[0],'X',b);
  const ww=r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command);
  same(ww.map(w=>[w.command,w.chip,w.slot,w.nibble]),Array.from({length:12},(_,j)=>[late[0].command,3,'X',1+3*j]));
  const expected=structuredClone(start.ring);deep.word(expected,'X',b);same(end.ring,expected,'NOP changes only 12 X tetras');
  // Check the full connected formatter for the two distinct fixture classes.
  same(b[0],'0');let zeroes=0;while(b[b.length-1-zeroes]==='0')zeroes++;
  const decimal=Number(b.slice(1,3))<=7;
  same([zeroes,decimal],decimal?[4,true]:[1,false]);
  const seq=deep.ips('EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D0');
  if(decimal)seq.push(0xF2);
  seq.push(...Array.from({length:zeroes+1},()=>[0xF3,0xF7,0xF1]).flat(),
    ...Array.from({length:8-zeroes},()=>[0xF4,0xF6]).flat(),...deep.ips('F4 EA EC 40 41 42 46'));
  while(!['marker','Z','W'].includes(slots[(slots.indexOf('P8')+seq.length)%15]))seq.push(0xE5);
  seq.push(...deep.ips('E5 E6 E8 E7'));
  same(late[0].command-reads[1].command+1,seq.length);deep.path(es,reads[1].command,'P8',seq);
  entry.endpoint(r,end,'P8');
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  return {prefix,boundaries:rows.length,readP8:reads[1].command,copyToX:late[0].command,
    all23LiveAtEveryActionBoundary:true,onlyXChangedByNOP:true,extraMarkers:['Z','W'],
    vOnlyInT:true,all23StoredAtEnd:false,workingExit:false,lastTwoMsChanged:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_ZW_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(deep.surface(o,probe.finish)));
  console.log('PASS frame boundaries:',JSON.stringify(entry.frameCheck(probe.run(o),'P8')));
  const r=probe.traced(o);console.log('PASS native P8 read:',JSON.stringify(check(r)));
  if(process.env.K1_ZW_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check};
