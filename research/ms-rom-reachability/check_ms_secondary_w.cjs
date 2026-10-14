#!/usr/bin/env node
'use strict';
// Read W through IK1303 after W/Q has left the 1F response in U.
// V may be clobbered; a composition must have backed it up before this call.
const assert=require('node:assert/strict');
const p=require('./probe_ms_shifted_swap.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const raw=m=>Array.from({length:12},(_,i)=>m[34-3*i].toString(16).toUpperCase()).join('');
const A=c=>Array.from({length:12},(_,i)=>c.r[3*i]);
const numeric=c=>Array.from({length:12},(_,i)=>c.m[1+3*i]);
function check(r) {
  assert.equal(r.before.U.slice(2,4),'1F');
  assert.equal(r.afterRegisters[9],r.before.W.slice(2));
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  for(let n=0;n<15;n++)if(n!==9)assert.equal(r.afterRegisters[n],r.beforeRegisters[n]);
  for(const n of Object.keys(r.before))if(n!=='V')assert.equal(r.after[n],r.before[n]);
  assert.equal(r.after.V.slice(0,2),r.before.V.slice(0,2));
  const changed=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>w.slot==='V'&&w.nibble<=34));
  assert.deepEqual(r.traced.primitives,[]);assert.ok(r.traced.events.every(e=>e.ip!==0xC9));
  const es=r.traced.events;
  const writerAt=es.findIndex(e=>e.stage==='shifted-swap'&&e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='X');
  assert.ok(writerAt>=0);const writer=es[writerAt].otherChips[4];
  const sourceAt=es.findLastIndex((e,i)=>i<writerAt&&e.otherChips?.[4].ip===0x53);
  assert.ok(sourceAt>=4);const source=es[sourceAt].otherChips[4];
  assert.equal(source.slot,'W');assert.equal(raw(source.m),r.before.W.slice(2));
  assert.deepEqual([source.l,source.s1,...[32,35,41].map(i=>source.r[i])],[1,6,5,0,5]);
  const prefix=es.slice(sourceAt-4,sourceAt).map(e=>e.otherChips[4]);
  assert.deepEqual(prefix.map(c=>[c.ip,c.slot]),[[0x6E,'Z'],[0x5E,'T'],[0x50,'U'],[0x52,'V']]);
  assert.equal(prefix[0].r[29],0);assert.equal(prefix[0].m[22],15);
  assert.deepEqual([prefix[1].m[34],prefix[1].m[31]],[1,4]);
  assert.deepEqual(A(writer),numeric(source));
  assert.deepEqual(es.slice(sourceAt,writerAt+3).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [[0x53,'W'],[0x4F,'Q'],[0x41,'P7'],[0x43,'P8'],[0x4D,'P9'],[0x60,'P10'],
     [0x37,'marker'],[0x27,'control'],[0x61,'X1'],[0x4E,'X'],[0x2A,'Y'],[0x39,'Z']]);
  const pair=es.slice(writerAt,writerAt+3),expected=structuredClone(pair[0].ring);
  for(let i=0;i<12;i++){expected.X[1+3*i]=source.m[1+3*i];expected.Y[1+3*i]=writer.m[1+3*i];}
  assert.deepEqual(pair[2].ring,expected,'all 630 ring tetras across the secondary X/Y output pair');
  const writes=r.traced.writes.filter(w=>w.command>=pair[0].command&&w.command<pair[2].command);
  assert.equal(writes.length,24);assert.ok(writes.every(w=>w.chip===4&&['X','Y'].includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
}
for(const values of [['111','222','333','444'],['-1E-99','-1.2345678E-42','-9.8765432E99','12345678']]) {
  const calc=p.prepare({values});p.finish(calc,{lifts:3,save:false});calc.runFrames(3);aligned(calc);
  // Reprepare the same native setup for each phase; the reader itself has
  // no synchronization or direct-state writes.
  for(const phaseOffset of [0,1,2]) {
    const c=phaseOffset===0?calc:p.prepare({values});
    if(phaseOffset!==0){p.finish(c,{lifts:3,save:false});c.runFrames(3);aligned(c);}
    const r=p.runPrepared(c,{lifts:2,phaseOffset,postSwap:[['П→X','3'],['П→X','3'],['F',',']],save:true});
    check(r);console.log('PASS:',JSON.stringify({values,phaseOffset}),'W -> P9 under 1F U; only backed-up V may change.');
  }
}
console.log('NOT nondestructive by itself: V must be saved and restored externally.');
