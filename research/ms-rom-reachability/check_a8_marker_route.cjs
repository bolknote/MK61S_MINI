#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {run,prepare,finish}=require('./probe_a8_marker_route.cjs');
const {aligned,trace}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const referenceRoute=fs.readFileSync(path.join(__dirname,'check_a8_single_route.py'),'utf8')
  .match(/ROUTE='''([\s\S]*?)'''/)[1].trim().split(/\s+/).map(s=>parseInt(s,16));
const accumulator=e=>Array.from({length:12},(_,i)=>e.r[3*i]);
const numeric=m=>Array.from({length:12},(_,i)=>m[1+3*i]);
const cases=[{}, {phaseOffset:1}, {phaseOffset:2}, {settleFrames:12},
  {placement:'before-address'}, {seedLowDigit:0},
  {values:['-1.2345678E-42','8.7654321E17','-23456789','34567891']}];
let firstDigest;
for(const options of cases) {
  const r=run(options);firstDigest??=digest(r.calc);
  const stages=Object.fromEntries(r.stages.map(s=>[s.label,s]));
  assert.equal(stages.address.pc,0xE0);assert.equal(stages.address.st35,7);
  assert.equal(stages.marker.st35,7,'recalling the precomputed marker preserves saved seven');
  const acIndex=r.traced.events.findIndex(e=>e.stage==='recall'&&e.ip===0xAC);
  assert.ok(acIndex>=0);
  const route=r.traced.events.slice(acIndex)
    .filter((e,i,es)=>!(e.ip===0xE5&&es[i-1]?.ip===0xE5));
  assert.deepEqual([route[0].pc,route[0].st35],[0xE0,7]);
  assert.deepEqual(route.slice(0,85).map(e=>e.ip),referenceRoute.slice(0,85));
  assert.deepEqual([route[5].m[34],route[69].m[34]],[6,7]);
  assert.equal(route[69].slot,'X');
  assert.equal(route[85].ip,0xD7,'the second read prevents the former single-A8 suffix');
  assert.equal(r.singles.length,0,'do not mislabel this as an EE-to-single-A8 invocation');
  const blocks=r.blocks.filter(b=>b.body[0].stage==='recall'&&b.body[0].slot==='V');
  assert.equal(blocks.length,1,'one finite four-word block in Ms');
  const b=blocks[0],es=r.traced.events;
  assert.deepEqual(b.body.map(e=>e.ip),[0xE7,0xA8,0xA8,0xA8]);
  assert.deepEqual(b.body.map(e=>e.slot),['V','W','Q','P7']);
  assert.deepEqual(b.body.map(e=>e.s1),[8,10,12,14]);
  assert.equal(b.after.s1,0);assert.equal(b.after.nextIp,0xE1);
  const at=es.findIndex(e=>e.command===b.body[0].command);
  const anchor=es[at-3];
  assert.deepEqual([anchor.ip,anchor.slot,anchor.m[22],anchor.s1],[0xE5,'Z',15,8]);
  assert.deepEqual(es.slice(at-2,at).map(e=>[e.ip,e.slot]),[[0xE6,'T'],[0xE8,'U']]);
  const expected=structuredClone(b.body[0].ring);
  let carried=accumulator(b.body[0]);
  assert.equal(carried.slice().reverse().map(v=>v.toString(16)).join(''),'600010000001');
  for(const event of b.body) {
    assert.deepEqual(accumulator(event),carried);
    const displaced=numeric(expected[event.slot]);
    for(let i=0;i<12;i++) expected[event.slot][1+3*i]=carried[i];
    carried=displaced;
  }
  assert.deepEqual(b.after.ring,expected,'all 630 ring tetras after the whole block');
  assert.deepEqual(accumulator(b.after),carried);
  assert.equal(b.writes.length,48,'exactly 48 writes across all THREE processors');
  assert.ok(b.writes.every(w=>w.chip===3&&[0xE7,0xA8].includes(w.ip)));
  assert.deepEqual(b.writes.map(w=>[w.slot,w.nibble]),b.body.flatMap(e=>
    Array.from({length:12},(_,i)=>[e.slot,1+3*i])));
  const expectedMs={...r.before,V:r.before.V.slice(0,2)+'600010000001',
    W:r.before.W.slice(0,2)+r.before.V.slice(2),
    Q:r.before.Q.slice(0,2)+r.before.W.slice(2),
    P7:r.before.P7.slice(0,2)+r.before.Q.slice(2)};
  assert.deepEqual(r.after,expectedMs,'all 112 Ms tetras over the complete final protocol');
  assert.deepEqual(r.traced.primitives,[],'no entry to C7/C8 addresses');
  assert.equal(stages.recall.ip,0x35);
  assert.equal(stages.recall.r2,0);
  assert.equal(stages.recall.r5,options.seedLowDigit??5);
  assert.equal(stages.recall.r23,7,'keyboard prefix is still abnormal even with R5=0');
  console.log('PASS:',JSON.stringify(options),
    'native Z marker; E7/A8x3 at V,W,Q,P7; all 630 tetras/48 writes; second EE reads header 7.');
}
const plain=prepare();finish(plain);aligned(plain);
assert.equal(digest(plain),firstDigest,'observers do not change complete reference state');
console.log('PASS: observed/unobserved full states agree:',firstDigest);

for(const placement of ['none','before-clear']) {
  const r=run({placement});
  assert.deepEqual(r.after,r.before,'negative marker placement leaves Ms unchanged');
  assert.equal(r.blocks.filter(b=>b.body[0].stage==='recall'&&b.body[0].slot==='V').length,0);
  if(placement==='none') assert.equal(r.singles.length,1,'old single call remains the no-marker control');
  else assert.equal(r.stages.find(s=>s.label==='clear-again').st35,0,'early marker loses the seven');
  console.log('PASS: negative placement control',placement);
}

// Read the exit as a real keyboard state. Zeroing R5 alone is NOT recovery:
// the very next Cx is decoded with an abnormal prefix and E5 uses Z again.
const noMode=run({seedLowDigit:0,values:['111','222','333','444']});
const cx=trace(noMode.calc,c=>c.press('Сx').runFrames(8),
  {extraIps:Array.from({length:256},(_,i)=>i),fullState:true});
assert.ok(cx.events.some(e=>e.ip===0xE5&&e.slot==='Z'&&e.m[22]===15&&e.nextIp===0xE6));
assert.ok(cx.events.some(e=>e.ip===0xEE&&e.slot==='V'),
  'a subsequent Cx reads the Ms word, demonstrating the surviving false anchor');
noMode.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
assert.notEqual(noMode.calc.displayText(),'5,','no safe arithmetic return is claimed');
assert.deepEqual(fullMsPages(aligned(noMode.calc)),noMode.after);
console.log('PASS: exit counterexample: even R5=0 retains false Z marker and does not compute 2 ENTER 3 + = 5.');
console.log('NOT K1: finite four-word shift into Ms, not pairwise exchange and not a recovered keyboard exit.');
