#!/usr/bin/env node
'use strict';
// One native rotation of the four upper Ms words; no safe return claimed.
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_swap.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const sourceKeys=['F',','],names=['P7','P8','P9','P10'];
function check(r) {
  const es=r.traced.events;
  const request=es.find(e=>e.stage==='upper-swap'&&e.ip===0xA2&&e.slot==='V');
  assert.ok(request);assert.deepEqual([request.r[32],request.r[35]],[5,2]);
  const expected={...r.before,U:r.before.U.slice(0,2)+'000000000000',
    V:r.before.V.slice(0,2)+'0000F0000000',
    W:r.before.W.slice(0,2)+'2F'+request.r[27].toString(16).toUpperCase()+r.before.U.slice(5),
    Q:r.before.Q.slice(0,2)+r.before.V.slice(2)};
  for(let i=0;i<4;i++)expected[names[i]]=r.before[names[i]].slice(0,2)+r.before[names[(i+1)%4]].slice(2);
  assert.deepEqual(r.after,expected);
  const regs=r.beforeRegisters.slice();regs[0]=r.before.P7.slice(2);regs[8]='000000000000';regs[9]='0000F0000000';
  assert.deepEqual(r.afterRegisters,regs);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  const at=es.findIndex(e=>e.stage==='upper-swap'&&e.otherChips?.[4].ip===0x3A);
  assert.ok(at>=0);const c=es[at].otherChips[4];
  const bufferAt=es.findLastIndex((e,i)=>i<at&&e.stage==='upper-swap'&&
    e.otherChips?.[4].ip===0xD4&&e.otherChips[4].slot==='Q');
  assert.ok(bufferAt>=0);const buffer=es[bufferAt].otherChips[4];
  assert.deepEqual([buffer.l,buffer.s1,...[37,38,40,41].map(i=>buffer.r[i])],
    [1,9,4,0,13,6],'exact control premises of the connected symbolic buffering proof');
  assert.equal(raw(buffer.r,2),r.before.P7.slice(2),'C already contains the whole original P7');
  assert.equal(raw(buffer.r,1),r.before.P8.slice(2),'B already contains the whole original P8');
  assert.deepEqual([0,1,2].map(i=>buffer.st[36+i]+16*buffer.st[39+i]),[0x29,0x3A,0x3A]);
  assert.deepEqual(es.slice(bufferAt,at+1).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [...['Q',...names].map(n=>[0xD4,n]),[0xC4,'marker'],[0x2C,'control'],[0x3B,'X1'],
      [0x2B,'X'],[0x60,'Y'],...['Z','T','U','V'].map(n=>[0x37,n]),[0x27,'W'],[0x61,'Q'],[0x3A,'P7']]);
  assert.ok(r.traced.writes.filter(w=>w.command>=es[bufferAt].command&&w.command<es[at].command&&
    Object.hasOwn(r.before,w.slot)&&w.nibble%3===1).every(w=>w.value===w.before),
    'the buffer is prepared before any of the four upper source words is overwritten');
  assert.equal(c.s1,5);assert.equal(raw(c.r,0),r.before.P7.slice(2));
  assert.deepEqual([0,1,2].map(l=>raw(c.st,l)),names.slice(1).map(n=>r.before[n].slice(2)),
    'all four original words are buffered before the first output, not synthesized by the test');
  const block=es.slice(at,at+5);
  assert.deepEqual(block.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [[0x3A,'P7'],[0x3A,'P8'],[0x3A,'P9'],[0x2A,'P10'],[0x39,'marker']]);
  const ring=structuredClone(block[0].ring);
  for(let i=0;i<4;i++)for(let j=0;j<12;j++)ring[names[i]][1+3*j]=block[0].ring[names[(i+1)%4]][1+3*j];
  assert.deepEqual(block[4].ring,ring,'all 630 ring tetras after the rotation');
  const writes=r.traced.writes.filter(w=>w.command>=block[0].command&&w.command<block[4].command);
  assert.equal(writes.length,48);assert.ok(writes.every(w=>w.chip===4&&w.nibble%3===1&&w.nibble<=34&&
    ((w.ip===0x3A&&names.slice(0,3).includes(w.slot))||(w.ip===0x2A&&w.slot==='P10'))));
  const changed=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>w.nibble<=34),'all Ms service fields remain unchanged throughout the probe');
}
function main() {
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true,
      values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
      upperValues:['-1E-99','-8.7654321E-17','333','444']})),
    {settleFrames:12,markerFrames:8}];
  let firstDigest;
  for(const options of cases){const r=p.run({...options,sourceKeys});check(r);firstDigest??=digest(r.calc);
    console.log('PASS:',JSON.stringify(options),'upper Ms rotate P7<-P8<-P9<-P10<-old P7; program preserved.');}
  const plain=p.prepare(cases[0]);p.finish(plain,{...cases[0],sourceKeys});plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS: observed/unobserved full state:',firstDigest);
  console.log('LIMIT: P9/P10 initially zero in these native fixtures. The arbitrary-word output suffix has a separate symbolic proof.');
  console.log('NOT a safe reader: the V marker and W:2F remain; repeated rotation/read/restore is not established.');
}
if(require.main===module)main();
module.exports={check};
