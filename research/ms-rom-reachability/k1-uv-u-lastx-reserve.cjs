#!/usr/bin/env node
'use strict';
// U reserve in the real numerical LastX without touching any incoming bank.
// Original ROM/native public keys only. Fixed schedule, no state choices.
const assert=require('node:assert/strict');
const cap=require('./k1-bank-v-capture.cjs'),uv=require('./k1-zero-uv-retained-reader.cjs');
const {recipes,writerTail}=require('./k1-uv-reader-reverse-writer-plan.cjs');
const {raw}=require('./probe_ms_two_markers.cjs'),{ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {guarded}=require('./arbitrary-bank-pair-zero-capture-keyboard-check.cjs');
const m4='0040F0000000';
function operation(c,o,record=()=>{}){
  uv.operation(c,o,s=>record('reader/'+s));
  for(const [stage,keys,frames=8] of [...recipes['payload-tail'],...writerTail.slice(0,8),
    ['get-u-top',['↔']],['cache-u',['K','-']]]){
    record(stage);c.pressSequence(keys).runFrames(frames);
  }
}
function run(o={}){return cap.run({...uv.base,...o},operation,['get-u-top','cache-u']);}
function check(r){
  const es=r.traced.events,at=s=>{const e=es.find(e=>e.stage===s&&e.ring);assert.ok(e,s);return e;};
  const p=r.beforeRegisters[0],u=r.before.U.slice(2),v=r.before.V.slice(2);
  const visible=e=>['X','Y','Z','T','X1'].map(w=>raw(e.ring[w]));
  assert.equal(new Set(r.beforeRegisters.concat(Object.values(r.before).map(w=>w.slice(2)))).size,23);
  assert.deepEqual(visible(at('get-u-top')),[m4,p,v,u,'000000000000']);
  const displayWrites=es.filter(e=>e.stage==='get-u-top'&&e.ip===0xE7);
  assert.equal(displayWrites.length,1);const formatter=displayWrites[0];
  assert.ok(['X','Z'].includes(formatter.slot),'only visible late formatter destinations admitted');
  assert.equal(raw(formatter.r,0),u,'late formatter retains all12 U fields');
  const expectedFormat=ringAt(r,formatter.command);
  [...u].reverse().forEach((n,i)=>{expectedFormat[formatter.slot][1+3*i]=parseInt(n,16);});
  assert.deepEqual(ringAt(r,formatter.command+1),expectedFormat,'exact late U formatter among all630');
  const redundant=formatter.slot==='Z'?u:v;
  assert.deepEqual(visible(at('cache-u')),[u,m4,redundant,u,m4]);
  const source=es.find(e=>e.stage==='cache-u'&&e.ip===0xEE),save=es.find(e=>e.stage==='cache-u'&&e.ip===0xE9),
    request=es.find(e=>e.stage==='cache-u'&&e.ip===0xA3);
  assert.ok(source&&save&&request);assert.equal(source.slot,'X');assert.equal(source.raw,u);assert.equal(save.slot,'X1');
  const expectedSave=ringAt(r,save.command);[...u].reverse().forEach((n,i)=>{expectedSave.X1[1+3*i]=parseInt(n,16);});
  assert.deepEqual(ringAt(r,save.command+1),expectedSave,'E9 saves exactly U in real LastX among all630');
  assert.equal(request.slot,'Z');const expectedRequest=ringAt(r,request.command);
  [28,31,34].forEach((n,i)=>{expectedRequest.Z[n]=[parseInt(u[2],16),7,2][i];});
  assert.deepEqual(ringAt(r,request.command+1),expectedRequest,'only redundant visible V request header changes');
  const end=at('done');assert.deepEqual(visible(end),[u,m4,'27'+u[2]+redundant.slice(3),u,u]);
  assert.deepEqual(Object.keys(end.ring).filter(w=>end.ring[w][22]===15),['marker','Y']);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters);assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(r.traced.writes.filter(w=>(Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)||w.nibble%3===0||
    w.nibble%3===2||[37,40].includes(w.nibble)).every(w=>w.before===w.value),
    'all incoming banks, programme and services retained even temporarily');
  return{options:r.options,p,u,v,visible:visible(end),all23BankWordsHeld:true,realLastXU:true,
    lateUFormatter:formatter.slot,redundantStackWordBeforeRequest:redundant,
    boundary:'full U reserve in LastX plus Y marker; no reverse writer or full K1; only redundant stack header changed, original Ms V held'};
}
function verify(o={}){
  const r=run(o),audit=check(r),plain=cap.prepare(r.options),g=guarded(plain);
  operation(g.proxy,r.options);plain.runFrames(3);aligned(plain);
  assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)),'fresh full native public-key mirror');
  r.traced.events.length=r.traced.writes.length=0;
  return{...audit,keys:g.counts.keys,bodyFrames:2*g.counts.keys+g.counts.extraFrames};
}
if(require.main===module)console.log(JSON.stringify(verify(process.argv[2]?JSON.parse(process.argv[2]):{})));
module.exports={operation,run,check,verify,m4};
