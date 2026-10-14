#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {normalization}=require('./check_ms_clone_numeric_x.cjs');
const marker='0000F0000000',zero='000000000000';
const copyRing=r=>Object.fromEntries(Object.entries(r).map(([n,v])=>[n,v.slice()]));
function check(r,{negative=false}={}) {
  assert.equal(r.options.tail,undefined,'this contract ends before a candidate write suffix');
  const es=r.traced.events,ww=r.traced.writes,source=r.beforeRegisters[0],oldV=r.before.V.slice(2);
  const norm=source===zero?undefined:normalization(source),q=norm&&norm.cuts+Number(norm.small);
  if(norm)assert.ok(negative?q<=4:q>=5,'declared capture formatter class');
  const stores=es.filter(e=>e.stage==='store-0'&&e.ip===0xD4);assert.equal(stores.length,1);
  const d4=stores[0],read=es.find(e=>e.stage==='store-0'&&e.ip===0xEE);
  assert.equal(read.slot,'V');assert.equal(d4.slot,'U');
  const after=es.find(e=>e.command===d4.command+1);assert.ok(after&&after.ring);assert.equal(after.ip,0xA5);
  const expected=copyRing(d4.ring);
  for(let j=0;j<12;j++)expected.U[j*3]=read.m[1+3*j];
  assert.deepEqual(after.ring,expected,'exact source V to P0 store, all 630 tetras');
  assert.deepEqual(ww.filter(w=>w.command===d4.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
    Array.from({length:12},(_,j)=>[3,'U',3*j,read.m[1+3*j]]));
  for(const stage of ['load-0a','load-0b']) {
    const reads=es.filter(e=>e.stage===stage&&e.ip===0xD6);assert.equal(reads.length,1);
    assert.equal(reads[0].slot,'U');assert.equal(raw(reads[0].m,0),source);
    const first=es.find(e=>e.stage===stage&&e.ip===0xE7&&e.command>reads[0].command);assert.ok(first);
    const body=es.filter(e=>e.command>=first.command&&e.command<first.command+4);
    assert.deepEqual(body.map(e=>[e.ip,e.slot]),[[0xE7,'X'],[0xA8,'Y'],[0xA8,'Z'],[0xA8,'T']]);
    const state=copyRing(first.ring);let carried=Array.from({length:12},(_,j)=>first.r[3*j]);
    for(const e of body) {const old=Array.from({length:12},(_,j)=>state[e.slot][1+3*j]);
      assert.deepEqual(Array.from({length:12},(_,j)=>e.r[3*j]),carried);
      for(let j=0;j<12;j++)state[e.slot][1+3*j]=carried[j];carried=old;}
    const end=es.find(e=>e.command===first.command+4);assert.ok(end&&end.ring);
    assert.equal(end.ip,0xA9);assert.deepEqual(end.ring,state,'complete visible lift, all 630 tetras');
    assert.deepEqual(ww.filter(w=>w.command>=first.command&&w.command<first.command+4)
      .map(w=>[w.chip,w.slot,w.nibble]),['X','Y','Z','T'].flatMap(n=>Array.from({length:12},(_,j)=>[3,n,1+3*j])));
  }
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[source,source,marker,zero]);
  assert.equal(r.afterRegisters[0],negative?source:oldV);
  for(let i=1;i<15;i++)assert.equal(r.afterRegisters[i],r.beforeRegisters[i]);
  assert.ok(r.beforeRegisters[3]!==zero,'P3 is independent and nonzero, not an undeclared zero scratch');
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  assert.ok(ww.filter(w=>[37,40].includes(w.nibble)).every(w=>w.before===w.value),'all M2 service tetras unchanged even transiently');
  assert.ok(ww.filter(w=>[36,39].includes(w.nibble)).every(w=>w.before===w.value),'all M1 service tetras unchanged even transiently');
  const msWrites=ww.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  if(!negative) {
    assert.deepEqual(r.after,r.before);assert.deepEqual(msWrites,[],'no changed Ms tetra, even transiently');
    assert.equal(raw(read.m),oldV);
  } else {
    assert.notEqual(oldV,source);assert.equal(raw(read.m),source,'negative control: second recall destroyed V before D4');
    assert.equal(r.after.V.slice(2),source);assert.ok(msWrites.length>0);
    assert.ok(es.some(e=>e.stage==='load-0b'&&e.ip===0xE7&&e.slot==='V'));
  }
  return {phase:r.options.phaseOffset??0,source,oldV,q,negative,
    p0:r.afterRegisters[0],sourceHeldInXY:true,other14RegistersHeld:true,allMsHeld:!negative,programHeld:true};
}
if(require.main===module) {
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset})),
    {incoming:'-1.23E-42'},{incoming:'-1E-99'},{incoming:'1'},
    {incoming:'0'},{incoming:'101',fullUpper:['1111','2222','3333','4444']}];
  const from=Number(process.env.K1_BANK_FROM??0),count=Number(process.env.K1_BANK_CASES??cases.length);
  if(process.env.K1_BANK_NEGATIVE)for(const incoming of ['-1.234E-42','1.2345678E42']) {
    const r=p.run({incoming});console.log('PASS negative capture:',JSON.stringify(check(r,{negative:true})));r.traced.events.length=r.traced.writes.length=0;
  } else for(const o of cases.slice(from,from+count)) {
    const r=p.run(o);console.log('PASS V capture:',JSON.stringify(check(r)));r.traced.events.length=r.traced.writes.length=0;
  }
  console.log('NOT a full swap: P0 holds old V and old P0 survives in X/Y; writing old P0 into V remains unproved.');
}
module.exports={check};
