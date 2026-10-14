#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zv-clear-timing.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const zw=require('./k1-zw-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {MK61}=require('./probe_ee_ring_source.cjs');
const same=assert.deepEqual;
const zero='000000000000',m='9990FFFFFFF0';
function endpoint(r,e,source='zero') {
  const first=r.initial??r.traced.events.find(x=>x.ring).ring;
  const original=snapshotFromRing(first),s=snapshotFromRing(e.ring);
  const [p,u,v,w,q,a]=[0,15,16,17,18,19].map(i=>original.words[i]);
  const want=original.words.slice();
  for(const [i,value] of [[0,w],[15,u],[16,source==='P7'?a:zero],[17,q],[18,p]])want[i]=value;
  same(s.words,want);same(['X1','X','Y','Z','T'].map(n=>raw(e.ring[n])),['00008FFFFFFF',a,u,m,v]);
  same(Object.entries(e.ring).filter(([,v])=>v[22]===15).map(([n])=>n).sort(),['Z','marker']);
  same(raw(e.ring.marker),'000FFFFFFFFF');
  same(s.program,original.program);same(s.services,original.services);
  same(original.words.filter(v=>![...s.words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))].includes(v)),[]);
}
function frameCheck(r,source='zero') {
  const original=snapshotFromRing(r.initial);same(new Set(original.words).size,23);
  same(r.rows.filter(x=>x.missing.length),[]);
  for(const e of r.rows) {
    const s=snapshotFromRing(e.ring);same(s.words.slice(1,15),original.words.slice(1,15));
    same(s.words.slice(19),original.words.slice(19));same(s.program,original.program);same(s.services,original.services);
  }
  for(const stage of ['immediate','done'])endpoint(r,r.rows.find(e=>e.stage===stage),source);
  return {boundaries:r.rows.length,all23Live:true,removedMarker:'V',vStillOnlyInT:true,fullK1:false};
}
function entryPrefix(r,boundaryName='fine-clear/0') {
  const prefix=deep.check(prefixView(r,'deep/tail-1',{deepTail:[['K','0']],deepTailPhases:[1]}));
  const renamed={...r,traced:{...r.traced,events:r.traced.events.map(e=>({...e,
    stage:e.stage===boundaryName?'deep/tail-2':e.stage}))}};
  const u=r.before.U.slice(2),a=r.before.P7.slice(2),v=r.before.V.slice(2);
  const enter=zw.operation(renamed,1,{reads:[['U',u,0xE0],['P7',a,0xE3]],
    targets:['X','Y','Z','T'],displaced:m,late:'X',lateValue:a,markers:['marker','Z','V'],
    final:{X:a,Y:u,Z:m,T:v},
    path:'9C 9E 8C 91 92 93 94 95 98 9A 93 94 95 98 9A 8D 4F EF E5 E6 ED EE E0 A7 E5 E5 E5 E5 E5 E5 E6 E8 E7 A8 A8 A8 A9 E1 91 92 93 94 95 98 9A 93 94 95 98 9A E2 E5 E5 E6 ED EE'});
  return {prefix,enter};
}
function check(r) {
  same(r.options.commandOffsets,[3]);same(r.options.afterClear??[],[]);
  const {prefix,enter}=entryPrefix(r);
  checks.protectedFields(r,[0],['U','V','W','Q']);
  const es=r.traced.events.filter(e=>e.stage==='fine-clear/0'),start=checks.boundary(r,'fine-clear/0'),end=checks.boundary(r,'done');
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['W',0x9E]]);
  same(es.filter(e=>[0xEE,0xE9,0xA3,0xA8,0xD4,0xD6].includes(e.ip)),[]);
  const writes=es.filter(e=>e.ip===0xE7);same(writes.length,1);const write=writes[0];
  repack.exactCopy(r,write,'V',zero);
  const ww=r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command);
  same(ww.map(w=>[w.command,w.chip,w.slot,w.nibble]),Array.from({length:12},(_,i)=>[write.command,3,'V',1+3*i]));
  const expected=structuredClone(start.ring);deep.word(expected,'V',zero);same(end.ring,expected,'all 630 tetras');
  endpoint(r,end);
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  return {prefix,enter,boundaries:rows.length,accepted:es.find(e=>e.ip===0x9C).command,
    clear:write.command,only12PrimaryWrites:true,all630EndpointTetras:true,all23Live:true,
    otherChipsNoRingWrites:true,workingExit:false,fullK1:false};
}
function surface(o) {
  function record(options){
    let stage='',ticks=0;const actions=[],seen=[],ds=['1,','2,','3,','4,'];
    const methods={press(k){actions.push(['key',k,stage]);return this;},pressSequence:MK61.prototype.pressSequence,
      runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n,stage]);return this;},
      tick(){ticks++;},displayText(){assert.match(stage,/(?:^|\/)attempt-\d\/display$/);const d=ds[seen.length];seen.push(d);return d;}};
    const c=new Proxy(methods,{get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden read '+String(k));return t[k];},
      set(){assert.fail('forbidden machine assignment');}});
    probe.finish(c,options,s=>{stage=s;});return {actions,seen,ticks};
  }
  const a=record(o);same(a,record({...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']}));
  same(a.seen,['1,','2,','3,','4,']);same(a.ticks,560*42);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0)+a.ticks/(560*42),
    fixedTicksBeforeCx:126,fixtureExcluded:true,keysClockAndPublicDisplayOnly:true};
}
if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_ZV_CLEAR_OPTIONS||'{}'),commandOffsets:[3]};
  console.log('PASS surface:',JSON.stringify(surface(o)));
  if(!process.env.K1_ZV_SKIP_FRAME)console.log('PASS frames:',JSON.stringify(frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS native:',JSON.stringify(check(r)));
  if(process.env.K1_ZV_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={endpoint,frameCheck,entryPrefix,check,surface};
