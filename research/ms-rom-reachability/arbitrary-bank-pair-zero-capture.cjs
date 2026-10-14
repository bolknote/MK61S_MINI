#!/usr/bin/env node
'use strict';
// A resource-preserving raw V capture candidate, NOT a complete pair.
// Original P0 is moved into T before P0 receives V. Zero is the physical
// late formatter source while the false marker is in Z. Only public keys.
const assert=require('node:assert/strict');
const cap=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');

function operation(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??2);
  const a=(s,k,n=8)=>{record(s);c.pressSequence(k).runFrames(n);};
  a('zero-capture-clear',['Сx','В↑','В↑','В↑','+']);
  a('zero-capture-load-p0a',['П→X','0']);
  a('zero-capture-load-p0b',['П→X','0']);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())a('zero-capture-marker-'+i,[k],12);
  for(let i=0;i<2;i++) {
    a('zero-capture-zero-'+i,['0']);
    a('zero-capture-nop-'+i,['K','0']);
  }
  a('zero-capture-store-v',['X→П','0']);
}

function check(r) {
  const es=r.traced.events,ww=r.traced.writes;
  const store=es.find(e=>e.stage==='zero-capture-store-v'&&e.ip===0xD4);
  assert.ok(store,'native raw D4 is required');assert.equal(store.slot,'U');
  const expected=ringAt(r,store.command),v=r.before.V.slice(2),p=r.beforeRegisters[0];
  [...v].reverse().forEach((digit,i)=>{expected.U[3*i]=parseInt(digit,16);});
  assert.deepEqual(ringAt(r,store.command+1),expected,'D4 only writes all 12 V tetras to P0');
  assert.deepEqual(ww.filter(w=>w.command===store.command).map(w=>[w.chip,w.slot,w.nibble]),
    Array.from({length:12},(_,i)=>[3,'U',3*i]));
  const beforeStore=es.find(e=>e.stage==='zero-capture-store-v'&&e.ring);
  const end=es.find(e=>e.stage==='done'&&e.ring);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(beforeStore.ring[n])),
    ['000000000000','000000000000','0000F0000000',p]);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),
    ['000000000000','000000000000','0000F0000000',p]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((w,i)=>i===0?v:w));
  assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(ww.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value),'all Ms preserved even temporarily');
  assert.ok(ww.filter(w=>w.nibble%3===0&&w.nibble<36&&w.slot!=='U')
    .every(w=>w.before===w.value),'no other ordinary register changes even temporarily');
  assert.ok(ww.filter(w=>w.nibble%3===2||[36,37,39,40].includes(w.nibble))
    .every(w=>w.before===w.value),'program and M1/M2 service tetras held');
  const original=[...r.beforeRegisters,...Object.values(r.before).map(w=>w.slice(2))];
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  assert.ok(original.every(w=>live.includes(w)),'all 23 incoming words remain live');
  assert.deepEqual(r.traced.primitives,[]);
  const late=es.filter(e=>e.stage==='zero-capture-store-v'&&[0xEE,0xE7].includes(e.ip));
  assert.deepEqual(late.map(e=>[e.ip,e.slot]),[[0xEE,'V'],[0xEE,'X'],[0xE7,'X']]);
  assert.equal(late[1].raw,'000000000000');
  return {options:r.options,p,v,D4:store.command,all23Live:true,
    inputDistinctWords:new Set(original).size,lateSourceAndTarget:'zero X -> X',
    boundary:'P0 now holds V; original P0 is retained in T; marker Z remains. This is not a completed pair.'};
}

function run(o={}) {return cap.run({...o,phaseOffset:o.phaseOffset??2},operation);}

function nativeMirror(r) {
  const c=cap.prepare(r.options);operation(c,r.options);c.runFrames(3);aligned(c);
  assert.deepEqual(JSON.parse(JSON.stringify(c)),JSON.parse(JSON.stringify(r.calc)),
    'complete native state equals a fresh run without passive trace');
}

if(require.main===module) {
  const cases=process.argv[2]?[JSON.parse(process.argv[2])]:[
    {incoming:'-1.2345678E42'},
    {incoming:'-1.234E-42',values:['111','222','-9.8765432E23','444']},
    {incoming:'-1.23E-42'},
    {incoming:'1'},
    {incoming:'0'},
    {incoming:'-1.2345678E42',phaseOffset:0},
    {incoming:'-1.2345678E42',phaseOffset:1},
    {incoming:'-1.2345678E42',values:['811','822','-9.8765432E23','4.44E12'],
      fullUpper:['9011','9022','9033','9044']},
  ];
  for(const options of cases) {
    const r=run(options);
    try {const result=check(r);nativeMirror(r);console.log('PASS raw zero-source V capture:',JSON.stringify(result));}
    catch(e) {
      process.exitCode=1;
      console.log('REJECTED raw zero-source V capture:',JSON.stringify({options,
        error:e.message,changedMs:Object.keys(r.before).filter(n=>r.after[n]!==r.before[n]),
        wantedP0:r.before.V.slice(2),actualP0:r.afterRegisters[0]}));
    }
    r.traced.events.length=r.traced.writes.length=0;
  }
}
module.exports={operation,run,check,nativeMirror};
