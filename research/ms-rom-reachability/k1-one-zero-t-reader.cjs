#!/usr/bin/env node
'use strict';
// Device-directed alternate construction: stop with a Y marker, retain
// P0 in Z, issue STORE0, then test the geometric T/LastX reader. The actual
// prefix has T=0, not a second P0 copy; record that distinction explicitly.
// This is not a key sweep or a declared full-bank exchange.
const assert=require('node:assert/strict'),cap=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs'),{snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const base={phaseOffset:2,p3:'777',values:['811','822','-9.8765432E23','4.44E12'],fullUpper:['9011','9022','9033','9044']};
function operation(c,o,record=()=>{}){
  c.runFrames(o.phaseOffset??2);const a=(s,k,n=8)=>{record(s);c.pressSequence(k).runFrames(n);};
  a('one-clear',['Сx','В↑','В↑','В↑','+']);a('one-p0a',['П→X','0']);a('one-p0b',['П→X','0']);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())a('one-marker'+i,[k],12);
  a('one-zero',['0']);a('one-nop',['K','0']);a('one-store0',['X→П','0']);
  a('one-read-t',['F','В↑']);
}
function run(o){
  const r=cap.run({...base,...o},operation,['one-read-t']),es=r.traced.events;
  const start=es.find(e=>e.stage==='one-read-t'&&e.ring),end=es.find(e=>e.stage==='done'&&e.ring);
  assert.ok(start&&end);const p=r.beforeRegisters[0],u=r.before.U.slice(2);
  const image=e=>['X','Y','Z','T'].map(n=>raw(e.ring[n]));
  assert.deepEqual(image(start),['000000000000','0000F0000000',p,'000000000000']);
  const prefix=snapshotFromRing(start.ring);
  assert.deepEqual(prefix.words.slice(1),[...r.beforeRegisters.slice(1),...Object.values(r.before).map(w=>w.slice(2))]);
  const source=es.find(e=>e.stage==='one-read-t'&&e.ip===0xEE&&e.slot==='T');
  const input=[...r.beforeRegisters,...Object.values(r.before).map(w=>w.slice(2))];
  assert.equal(new Set(input).size,23);
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  const plain=cap.prepare(r.options);operation(plain,r.options);plain.runFrames(3);aligned(plain);
  assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)));
  const report={options:r.options,initialP0:p,originalU:u,P0BeforeLastX:prefix.words[0],frontier:image(start),readT:source&&{command:source.command,raw:source.raw},
    result:image(end),lost:input.filter(w=>!live.includes(w)),
    changedMs:Object.keys(r.before).filter(n=>r.before[n]!==r.after[n]),
    selected:es.filter(e=>e.stage==='one-read-t'&&[0x9C,0xEE,0xE7,0xA8,0xA3,0x46].includes(e.ip))
      .map(e=>({command:e.command,ip:e.ip,slot:e.slot,raw:e.raw,nextIp:e.nextIp})),
    observerIndependent:true,boundary:'two structural native T-reader alternatives, not a full pair/universal domain'};
  if(source)assert.equal(source.raw,'000000000000','T is actually zero, not original P0');
  assert.ok(es.filter(e=>e.stage==='one-read-t'&&e.ip===0xEE).every(e=>e.raw!==p),'this T/LastX route never reads original P0');
  r.traced.events.length=r.traced.writes.length=0;return report;
}
if(require.main===module)for(const incoming of ['-1.2345678E42','-1.234E-42'])console.log(JSON.stringify(run({incoming})));
module.exports={operation,run};
