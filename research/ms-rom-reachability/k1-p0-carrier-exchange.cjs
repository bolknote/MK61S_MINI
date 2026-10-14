#!/usr/bin/env node
'use strict';
// Proposed complete V/P0 pair. No success claim until check() passes a native
// run. markerActions must be a separately established maker of carrierWord.
const assert=require('node:assert/strict');
const capture=require('./k1-bank-v-capture.cjs');
const retained=require('./k1-bank-marker-tail-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function finish(c,o={},record=()=>{}) {
  assert.ok(Array.isArray(o.markerActions)&&o.markerActions.length,'supply an established fixed-key marker maker');
  retained.operation(c,{...o,tail:undefined,recoverCapture:true},record);
  const act=(name,keys)=>{record(name);c.pressSequence(keys).runFrames(o.settleFrames??8);};
  o.markerActions.forEach((keys,i)=>act('carrier-marker-'+i,keys));
  const actions=[['save-marker',['X→П','0']],['push-marker',['П→X','0']],
    ['lastx-v-f',['F']],['lastx-v',['В↑']],['lastx-p-f',['F']],['lastx-p',['В↑']],
    ['indirect-p',['K','X→П',o.indirectKey??'0']],['p-to-t-marker',['П→X','0']],['write-v',['↔']],
    ['drop-marker',['П→X','0']],['rotate-0',['F',',']],['rotate-1',['F',',']],
    ['rotate-2',['F',',']],['restore-v',['X→П','0']]];
  for(const [name,keys] of actions)act(name,keys);
  return c;
}
const run=(o={})=>capture.run(o,finish);
function check(r) {
  const es=r.traced.events,ww=r.traced.writes,p=r.beforeRegisters[0],v=r.before.V.slice(2);
  const m=r.options.carrierWord??'0020F0100000';
  assert.ok(['0020F0100000','0010F7000000','0040F0000000'].includes(m),'a locally studied carrier is required');
  const first=n=>{const e=es.find(e=>e.stage===n&&e.ring);assert.ok(e,n);return e;};
  const visible=e=>['X','Y','Z','T'].map(n=>raw(e.ring[n]));
  assert.deepEqual(visible(first('save-marker')),[m,p,v,v]);
  assert.deepEqual(visible(first('indirect-p')),[p,v,m,m]);
  assert.equal(raw(first('indirect-p').ring.U,0),m);
  const indirect=es.filter(e=>e.stage==='indirect-p'&&[0xD6,0xD4].includes(e.ip));
  assert.deepEqual(indirect.map(e=>[e.ip,e.slot]),[[0xD6,'U'],[0xD4,'U'],[0xD4,'U']]);
  assert.equal(raw(indirect[0].m,0),m);
  const state=first('p-to-t-marker');assert.deepEqual(visible(state),[p,v,m,m]);
  assert.equal(raw(state.ring.U,0),p);
  assert.deepEqual(visible(first('write-v')),[p,p,v,m]);
  const writers=es.filter(e=>e.stage==='write-v'&&e.ip===0xE9&&e.slot==='V');
  assert.ok(writers.length>=1,'at least one real E9(V)');assert.ok(writers.every(e=>raw(e.r,0)===p));
  assert.deepEqual(visible(first('rotate-0')),[p,p,p,v]);
  assert.deepEqual(Object.keys(first('rotate-0').ring).filter(n=>first('rotate-0').ring[n][22]===15),['marker']);
  const end=first('done');assert.equal(raw(end.ring.X),v);
  assert.equal(r.afterRegisters[0],v);
  for(let i=1;i<15;i++)assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
  assert.deepEqual(r.after,{...r.before,V:r.before.V.slice(0,2)+p});
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(ww.filter(w=>w.nibble%3===2).every(w=>w.before===w.value),
    'the manual pair does not change even a temporary program tetra');
  assert.ok(ww.filter(w=>w.nibble%3===0&&w.nibble<36&&w.slot!=='U').every(w=>w.before===w.value),
    'no other ordinary register even transiently changed');
  assert.ok(ww.filter(w=>Object.hasOwn(r.before,w.slot)&&w.slot!=='V'&&w.nibble%3===1)
    .every(w=>w.before===w.value),'other seven Ms held even transiently');
  assert.ok(ww.filter(w=>[36,37,39,40].includes(w.nibble)).every(w=>w.before===w.value),
    'all M1/M2 service tetras held even transiently');
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {p,v,p0:r.afterRegisters[0],msV:r.after.V,other14RegistersHeld:true,other7MsHeld:true,programHeld:true};
}
function brief(r) {
  const stages=r.traced.events.filter(e=>e.ring&&r.traced.events.find(x=>x.stage===e.stage)===e)
    .filter(e=>!['clear','marker','load','store','recall','normal','retained'].some(n=>e.stage.startsWith(n)))
    .map(e=>({stage:e.stage,words:Object.fromEntries(['X1','X','Y','Z','T'].map(n=>[n,raw(e.ring[n])])),p0:raw(e.ring.U,0)}));
  return {stages,registers:r.afterRegisters.map((v,i)=>[i,r.beforeRegisters[i],v]).filter(x=>x[1]!==x[2]),
    ms:Object.entries(r.after).filter(([n,v])=>r.before[n]!==v),programHeld:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    paths:r.traced.events.filter(e=>['indirect-p','write-v'].includes(e.stage)&&[0xD6,0xD4,0xE9,0xEE,0xE7].includes(e.ip))
      .map(e=>[e.stage,e.command,e.ip.toString(16),e.slot,e.raw,raw(e.r,0),e.nextIp.toString(16)])};
}
if(require.main===module) {
  const o=JSON.parse(process.argv[2]||'{}'),r=run(o);
  console.log(JSON.stringify(brief(r),null,2));console.log('PASS native pair:',JSON.stringify(check(r)));
}
module.exports={finish,run,check,brief};
