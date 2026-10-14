#!/usr/bin/env node
'use strict';
// Canonical U reserve: native U/V reader, three ordinary ROLLs, |x| saves
// the original U in real LastX, clear result, then read actual LastX back.
// No conditional marker/carrier import or ordinary-register scratch.
const assert=require('node:assert/strict');
const uv=require('./k1-zero-uv-retained-reader.cjs'),cap=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs'),{ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {guarded}=require('./arbitrary-bank-pair-zero-capture-keyboard-check.cjs');
function operation(c,o,record=()=>{}){
  uv.operation(c,o,s=>record('reader/'+s));
  const act=(s,k)=>{record(s);c.pressSequence(k).runFrames(8);};
  for(let i=0;i<3;i++)act('canonical-roll-'+i,['F',',']);
  act('canonical-abs',['K','4']);act('canonical-clear',['Сx']);act('canonical-recall',['F','В↑']);
}
function run(o={}){return cap.run({...uv.base,...o},operation,['canonical-abs','canonical-recall']);}
function check(r){
  const es=r.traced.events,at=s=>{const e=es.find(e=>e.stage===s&&e.ring);assert.ok(e,s);return e;},u=r.before.U.slice(2);
  assert.equal(new Set(r.beforeRegisters.concat(Object.values(r.before).map(w=>w.slice(2)))).size,23);
  const normal=e=>assert.deepEqual(Object.keys(e.ring).filter(w=>e.ring[w][22]===15),['marker']);
  normal(at('canonical-abs'));assert.equal(raw(at('canonical-abs').ring.X),u);
  const source=es.find(e=>e.stage==='canonical-abs'&&e.ip===0xEE),save=es.find(e=>e.stage==='canonical-abs'&&e.ip===0xE9);
  assert.ok(source&&save);assert.deepEqual([source.slot,source.raw,save.slot],['X',u,'X1']);
  const expected=ringAt(r,save.command);[...u].reverse().forEach((n,i)=>{expected.X1[1+3*i]=parseInt(n,16);});
  assert.deepEqual(ringAt(r,save.command+1),expected,'exact U->real LastX E9 among all630');
  const cleared=at('canonical-recall');normal(cleared);
  assert.equal(raw(cleared.ring.X),'000000000000');assert.equal(raw(cleared.ring.X1),u);
  const reread=es.find(e=>e.stage==='canonical-recall'&&e.ip===0xEE);assert.ok(reread);
  assert.deepEqual([reread.slot,reread.raw],['X1',u],'actual LastX buffer read, not a false-marker synthetic source');
  const end=at('done');normal(end);assert.equal(raw(end.ring.X),u);assert.equal(raw(end.ring.X1),u);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters);assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(r.traced.writes.filter(w=>(Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)||w.nibble%3===0||
    w.nibble%3===2||[37,40].includes(w.nibble)).every(w=>w.before===w.value),
    'all23 original banks, programme and services unchanged even temporarily');
  return{options:r.options,u,actualLastXSource:'X1',all23BankWordsHeld:true,canonicalMarkerOnly:true,
    boundary:'U stored and independently read from real LastX after clearing X; no reverse writer or full K1'};
}
function verify(o={}){
  const r=run(o),out=check(r),plain=cap.prepare(r.options),g=guarded(plain);
  operation(g.proxy,r.options);plain.runFrames(3);aligned(plain);
  assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)),'fresh full native public-key mirror');
  r.traced.events.length=r.traced.writes.length=0;
  assert.equal(g.counts.keys,30);assert.equal(2*g.counts.keys+g.counts.extraFrames,228+r.options.phaseOffset);
  return{...out,keys:g.counts.keys,bodyFrames:2*g.counts.keys+g.counts.extraFrames};
}
if(require.main===module)console.log(JSON.stringify(verify(process.argv[2]?JSON.parse(process.argv[2]):{})));
module.exports={operation,run,check,verify};
