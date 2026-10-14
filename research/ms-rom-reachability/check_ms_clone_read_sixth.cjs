#!/usr/bin/env node
'use strict';
// Conditional continuation: four trailing zeros route the first formatter
// to V, then key 25 reaches EE(P8). The sixth word reaches X or U according
// to its canonical format class. Visible markers and pending requests remain.
const assert=require('node:assert/strict');
const p=require('./probe_ms_clone_load_x.cjs');
const {checkClones,release}=require('./check_ms_marker_clone_w.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {normalization}=require('./check_ms_clone_numeric_x.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {createHash}=require('node:crypto');
const m='0000F0000000',h='958912340000',g='958912345678',zero='000000000000';
const upper=['P7','P8','P9','P10'];
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q',...upper];
function check(r) {
  const es=r.traced.events,stage='clone-load-tail-0',b=r.before.P8.slice(2);
  assert.ok([0,1,2].includes(r.options.phaseOffset));assert.equal(r.beforeRegisters[2],h);
  assert.deepEqual(r.options.tailActions,[['F',',']]);assert.equal(checkClones(r).length,1);
  assert.equal(r.options.tailLeadFrames,undefined);
  const start=es.find(e=>e.stage===stage&&e.ring);assert.ok(start);
  assert.deepEqual(['X','Y','Z','T','U','V','W','Q'].map(n=>raw(start.ring[n])),[h,m,m,zero,g,h,m,g]);
  const at=es.findIndex(e=>e.stage===stage&&e.ip===0xE9);assert.ok(at>=0);
  const copy=es[at];assert.equal(copy.slot,'U');assert.equal(raw(copy.r,0),h);
  const expected=structuredClone(copy.ring);
  for(let i=0;i<12;i++)expected.U[1+3*i]=copy.r[3*i];
  assert.deepEqual(es[at+1].ring,expected);
  const writes=r.traced.writes.filter(w=>w.command===copy.command);
  assert.equal(writes.length,12);assert.ok(writes.every(w=>w.slot==='U'&&w.nibble%3===1&&w.nibble<=34));
  assert.deepEqual(es.slice(at+1,at+4).map(e=>[e.ip,e.slot]),[[0xA2,'V'],[0xA2,'W'],[0xA3,'Q']]);
  const ee=es.findIndex(e=>e.stage===stage&&e.command>copy.command&&e.ip===0xEE);
  assert.equal(es[ee].slot,'P8');assert.equal(es[ee].raw,b);
  assert.equal(es[ee].s1,13);assert.equal(es[ee].r[38],12);assert.equal(es[ee].r[41],15);
  assert.equal(es[ee].st[36]+16*es[ee].st[39],0xE3);
  const {seq,cuts,small}=normalization(b),destination=cuts+Number(small)<=5?'X':'U';
  assert.deepEqual(es.slice(ee,ee+seq.length+1).map(e=>[e.ip,e.slot]),
    [...seq,0x40].map((ip,i)=>[ip,slots[(12+i)%15]]));
  const ret=es.findIndex(e=>e.stage===stage&&e.command>es[ee].command&&e.ip===0xE7);
  const result=checkSwapBlock(r,ret,1);
  assert.equal(result.body[0].slot,destination);assert.equal(raw(result.body[0].r,0),b);
  const form=[0x40,0x41,0x42,0x46],first=(12+seq.length)%15;
  while(!['marker','Y','Z','W'].includes(slots[(first+form.length)%15]))form.push(0xE5);
  form.push(0xE5,0xE6,0xE8,0xE7,0x47);
  assert.deepEqual(es.slice(ee+seq.length,ret+2).map(e=>[e.ip,e.slot]),
    form.map((ip,i)=>[ip,slots[(first+i)%15]]));
  for(const n of upper)assert.equal(r.after[n],r.before[n]);
  assert.ok(r.traced.writes.filter(w=>upper.includes(w.slot)&&w.nibble%3===1).every(w=>w.before===w.value));
  assert.deepEqual(['U','V','W','Q'].map(n=>r.after[n].slice(2)),[destination==='U'?b:h,h,m,'258912345678']);
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[destination==='X'?b:h,m,m,zero]);
  if(b==='003022220000')assert.equal(r.traced.display,'2222,');
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(e=>e.ip!==0xC9));
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>[6,10,14].includes(i)?m:v));
  return {source:b,destination,suppressed:cuts,decimal:small,copyU:copy.command,
    readSixth:es[ee].command,returnWrite:result.body[0].command,display:r.traced.display,upperPreserved:true};
}
if(require.main===module) {
  const base={phaseOffset:2,sourceValue:'-1.234E-42',tailActions:[['F',',']]};
  const cases=[base,
    {...base,fullUpper:['1111','-1.23E-42','3333','4444']},
    {...base,fullUpper:['1111','-1.2E-42','3333','4444']},
    {...base,fullUpper:['1111','-1E-99','3333','4444']},
    {...base,phaseOffset:0,fullUpper:['-7.654321E23','1.2345678E42','8.7654321E-17','-1E-99']},
    {...base,phaseOffset:1,fullUpper:['1111','1E7','3333','4444']}];
  if(process.env.MS_CLONE_SIXTH_UNOBSERVED) {
    const o=cases[2],r=p.run(o);check(r);
    const expected=JSON.parse(JSON.stringify(r.calc)),result=structuredClone(r.result);release(r);
    const c=p.prepare(o),plain=p.finish(c,o);c.runFrames(3);aligned(c);
    assert.deepEqual(plain,result);assert.deepEqual(JSON.parse(JSON.stringify(c)),expected);
    console.log('PASS sixth-word observed/unobserved, every serialized field:',
      createHash('sha256').update(JSON.stringify(c)).digest('hex'));
  } else {
    const from=Number(process.env.MS_CLONE_SIXTH_FROM??0),count=Number(process.env.MS_CLONE_SIXTH_CASES??cases.length);
    for(const o of cases.slice(from,from+count)) {
      const r=p.run(o);console.log('PASS conditional sixth-word read:',JSON.stringify(o),JSON.stringify(check(r)));release(r);
    }
  }
}
module.exports={check};
