#!/usr/bin/env node
'use strict';
// Native P7/P8 exchange, not an intact-Ms readout or a safe exit.
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_swap.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const marker='0000F0000000';
function check(r) {
  const es=r.traced.events;
  const request=es.find(e=>e.stage==='upper-swap'&&e.ip===0xA2&&e.slot==='V');
  assert.ok(request);assert.deepEqual([request.r[32],request.r[35]],[4,1]);
  const expectedW=r.before.W.slice(0,2)+'1F'+request.r[27].toString(16).toUpperCase()+r.before.U.slice(5);
  assert.deepEqual(r.after,{...r.before,
    U:r.before.U.slice(0,2)+'000000000000',V:r.before.V.slice(0,2)+marker,
    W:expectedW,Q:r.before.Q.slice(0,2)+r.before.V.slice(2),
    P7:r.before.P7.slice(0,2)+r.before.P8.slice(2),P8:r.before.P8.slice(0,2)+r.before.P7.slice(2)});
  const regs=r.beforeRegisters.slice();
  regs[0]=r.before.P7.slice(2);regs[8]='000000000000';regs[9]=marker;
  assert.deepEqual(r.afterRegisters,regs);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  const at=es.findIndex(e=>e.stage==='upper-swap'&&e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='P7');
  assert.ok(at>=0);const writer=es[at].otherChips[4];
  const sourceAt=es.findLastIndex((e,i)=>i<at&&e.otherChips?.[4].ip===0x53);
  const source=es[sourceAt].otherChips[4];
  assert.equal(source.slot,'P8');assert.equal(raw(source.m),r.before.P8.slice(2));
  assert.deepEqual([source.l,source.s1,...[32,35,41].map(i=>source.r[i])],[1,6,5,0,5]);
  const prefix=es.slice(sourceAt-4,sourceAt).map(e=>e.otherChips[4]);
  assert.deepEqual(prefix.map(c=>[c.ip,c.slot]),[[0x6E,'V'],[0x5E,'W'],[0x50,'Q'],[0x52,'P7']]);
  assert.equal(prefix[0].r[29],0);assert.equal(prefix[0].m[22],15);
  assert.deepEqual([prefix[1].m[34],prefix[1].m[31]],[1,4]);
  assert.equal(raw(writer.r,0),r.before.P8.slice(2));assert.equal(raw(writer.m),r.before.P7.slice(2));
  assert.deepEqual(es.slice(sourceAt,at+3).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [[0x53,'P8'],[0x4F,'P9'],[0x41,'P10'],[0x43,'marker'],[0x4D,'control'],[0x60,'X1'],
      ...['X','Y','Z','T','U','V'].map(n=>[0x37,n]),[0x27,'W'],[0x61,'Q'],
      [0x4E,'P7'],[0x2A,'P8'],[0x39,'P9']]);
  const pair=es.slice(at,at+3),ring=structuredClone(pair[0].ring);
  for(let i=0;i<12;i++){ring.P7[1+3*i]=source.m[1+3*i];ring.P8[1+3*i]=writer.m[1+3*i];}
  assert.deepEqual(pair[2].ring,ring,'all 630 ring tetras after the exchange');
  const writes=r.traced.writes.filter(w=>w.command>=pair[0].command&&w.command<pair[2].command);
  assert.equal(writes.length,24);assert.ok(writes.every(w=>w.chip===4&&w.nibble%3===1&&w.nibble<=34&&
    ((w.ip===0x4E&&w.slot==='P7')||(w.ip===0x2A&&w.slot==='P8'))));
  const changed=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>['U','V','W','Q','P7','P8'].includes(w.slot)&&w.nibble<=34),
    'P9/P10 and all Ms service fields stay intact throughout the probe');
}
function checkLostExit(lost) {
  const es=lost.traced.events;
  assert.notEqual(lost.before.P7,lost.before.P8);
  assert.ok(es.some(e=>e.stage==='upper-after-0'&&e.ip===0x9C&&e.slot==='W'&&e.nextIp===0x9E));
  const at=es.findIndex(e=>e.stage==='upper-after-0'&&e.ip===0xE7&&e.slot==='P7');
  assert.ok(at>=0);assert.deepEqual(es.slice(at,at+3).map(e=>[e.ip,e.slot]),
    [[0xE7,'P7'],[0x47,'P8'],[0x49,'P9']]);
  assert.equal(es[at].raw,lost.before.P8.slice(2));assert.equal(raw(es[at].r,0),'000000000000');
  assert.equal(raw(es[at+1].r,0),lost.before.P8.slice(2),'E7 briefly holds the displaced sixth word in A');
  assert.equal(raw(es[at+2].r,0),raw(es[at+1].st,0),'47 discards it and restores the old ST lane');
  assert.equal(raw(es.find(e=>e.stage==='upper-after-1'&&e.ring).ring.P7),'000000000000',
    'Cx has already cleared the sixth word before the store key');
  assert.equal(lost.after.P7,lost.before.P7);assert.equal(lost.after.P8,lost.before.P7);
  assert.notEqual(lost.afterRegisters[1],lost.before.P8.slice(2));assert.deepEqual(lost.afterProgram,lost.beforeProgram);
}
function main() {
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true,
      values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
      upperValues:['-1E-99','-8.7654321E-17','333','444']})),
    {settleFrames:12,markerFrames:8}];
  let firstDigest;
  for(const options of cases){const r=p.run(options);check(r);firstDigest??=digest(r.calc);
    console.log('PASS:',JSON.stringify(options),'exact P7/P8 exchange; declared lower-Ms damage only; program preserved.');}
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS: observed/unobserved full state:',firstDigest);
  const visible=p.run({visibleLifts:0});
  assert.ok(visible.traced.events.some(e=>e.stage==='upper-swap'&&e.ip===0xA3&&e.slot==='Z'));
  assert.ok(!visible.traced.events.some(e=>e.stage==='upper-swap'&&e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='P7'));
  assert.equal(visible.after.P7,visible.before.P7);assert.equal(visible.after.P8,visible.before.P8);
  console.log('PASS: leaving the visible Y marker diverts the request to Z and does not exchange P7/P8.');
  const lost=p.run({phaseOffset:2,afterKeys:[['Сx'],['X→П','1']]});
  checkLostExit(lost);
  console.log('PASS: phase-2 negative control: Cx accepts false W:1F and loses the sixth word before store P1.');
  console.log('NOT an intact-Ms operation: V marker and W:1F remain. No safe sixth-word readout claimed.');
}
if(require.main===module)main();
module.exports={check,checkLostExit};
