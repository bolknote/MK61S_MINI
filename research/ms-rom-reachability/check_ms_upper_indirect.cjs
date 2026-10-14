#!/usr/bin/env node
'use strict';
// Two complete upper words are saved, but the Ms bank is NOT restored.
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_indirect.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const marker='0000F0000000';
function check(r) {
  const es=r.traced.events,stage=es.filter(e=>e.stage==='upper-after-0');
  const request=es.find(e=>e.stage==='upper-swap'&&e.ip===0xA2&&e.slot==='V');
  assert.ok(request);
  const expectedW=r.before.W.slice(0,2)+'1F'+request.r[27].toString(16).toUpperCase()+r.before.U.slice(5);
  assert.deepEqual(r.after,{...r.before,
    U:r.before.U.slice(0,2)+'000000000000',V:r.before.V.slice(0,2)+marker,
    W:expectedW,Q:r.before.Q.slice(0,2)+r.before.V.slice(2),
    P7:r.before.P7.slice(0,2)+r.before.P8.slice(2),P8:r.before.P8.slice(0,2)+r.before.P7.slice(2)});
  const regs=r.beforeRegisters.slice();
  regs[0]=r.before.P7.slice(2);regs[1]=r.before.P8.slice(2);
  regs[5]='007000000001';regs[8]='000000000000';regs[9]=marker;
  assert.deepEqual(r.afterRegisters,regs);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  assert.equal(r.beforeRegisters[5],'000010000000');
  assert.equal(r.beforeRegisters[12],'000010000000');

  const pointer=stage.find(e=>e.ip===0xD6);
  assert.ok(pointer&&['Y','P8'].includes(pointer.slot));
  assert.equal(raw(pointer.m,0),'000010000000');
  assert.deepEqual([pointer.r[29],pointer.r[32],pointer.r[35],pointer.r[26],pointer.s1],[13,12,1,15,6]);
  assert.equal(pointer.sp[0],0x2F);
  const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  const seq=[0xD6,...Array.from({length:7},()=>[0x2F,0x20]).flat(),0x2F,0x21,0x23,0x25];
  let position=(slots.indexOf(pointer.slot)+seq.length)%15;
  while(slots[position]!=='V'){seq.push(1);position=(position+1)%15;}
  seq.push(1,...Array(13).fill(2),3,4,0xBA,0xCB,0xDD,0xD4,0x26,0x28,0x7E,0x71,0xAA,
    ...Array(6).fill(0xE5),0xE6,0xED,0xEE,0xAB,0xAD,0xA4,1,2,2,3,4,0xBA,0xCB,0xDD,0xD4);
  const path=stage.slice(stage.indexOf(pointer),stage.indexOf(pointer)+seq.length);
  assert.deepEqual(path.map(e=>[e.ip,e.slot]),seq.map((ip,i)=>[ip,slots[(slots.indexOf(pointer.slot)+i)%15]]),
    'the complete native path matches every connected command in the symbolic proof');
  for(const e of path)if([1,0xE5].includes(e.ip))
    assert.equal(e.m[22]===15,['V','marker'].includes(e.slot),'native marker premise for '+e.slot);
  const at=stage.findIndex(e=>e.ip===0xDD&&e.slot==='P7'&&e.nextIp===0xD4);
  assert.ok(at>=0);assert.equal(raw(stage[at].r,0),'007000000001');
  assert.deepEqual(stage.slice(at,at+8).map(e=>[e.ip,e.slot]),
    [[0xDD,'P7'],[0xD4,'P8'],[0x26,'P9'],[0x28,'P10'],
      [0x7E,'marker'],[0x71,'control'],[0xAA,'X1'],[0xE5,'X']]);
  const aa=stage[at+6];
  assert.deepEqual([aa.r[30],aa.r[33]],[1,4]);
  const read=stage.findIndex((e,i)=>i>at&&e.ip===0xEE&&e.slot==='P7');
  assert.ok(read>=0);assert.equal(stage[read].raw,r.before.P8.slice(2));
  assert.deepEqual(stage.slice(read-3,read+4).map(e=>[e.ip,e.slot]),
    [[0xE5,'V'],[0xE6,'W'],[0xED,'Q'],[0xEE,'P7'],[0xAB,'P8'],[0xAD,'P9'],[0xA4,'P10']]);
  const write=stage.findIndex((e,i)=>i>read&&e.ip===0xD4&&e.slot==='V');
  assert.ok(write>=0);assert.equal(stage[write-1].ip,0xDD);
  assert.equal(stage[write-1].slot,'U');
  assert.equal(raw(stage[write-1].r,0),r.before.P8.slice(2));
  assert.equal(stage[write].nextIp,0xA5);
  const writes=r.traced.writes.filter(w=>w.command===stage[write].command);
  assert.equal(writes.length,12);
  for(const w of writes) {
    assert.equal(w.chip,3);assert.equal(w.ip,0xD4);assert.equal(w.slot,'V');
    assert.ok(w.nibble%3===0&&w.nibble<=33);
    assert.equal(w.value,stage[read].m[w.nibble+1]);
  }
  const begin=stage[0].command;
  const changed=r.traced.writes.filter(w=>w.command>=begin&&
    Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.deepEqual(changed,[],'indirect store does not change any Ms tetra, even temporarily');
  assert.ok(stage.some((e,i)=>i>write&&e.ip===0x9C&&e.slot==='control'&&e.nextIp===0x9E));
  const formatters=stage.filter((e,i)=>i>write&&e.ip===0xE7&&e.nextIp===0x47);
  assert.ok(formatters.length>0);
  for(const e of formatters) {
    assert.ok(['X','P7'].includes(e.slot));
    assert.equal(raw(e.r,0),r.before.P8.slice(2));
    if(e.slot==='P7')assert.equal(e.raw,raw(e.r,0),'redirected formatter writes the same number, not a different one');
  }
  return {pointerSlot:pointer.slot,firstControl:stage.find(e=>e.ip===0x9C&&e.nextIp===0x9E).slot,
    formatterSlots:formatters.map(e=>e.slot)};
}
function main() {
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true,
      values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
      upperValues:['-1E-99','-8.7654321E-17','333','444']})),
    {settleFrames:12,markerFrames:8,stress:true},
    {phaseOffset:1,stress:true,upperValues:['0','222','333','444']}];
  let firstDigest;const pointerSlots=new Set();
  for(const options of cases) {
    const r=p.run(options),route=check(r);pointerSlots.add(route.pointerSlot);
    firstDigest??=digest(r.calc);
    console.log('PASS:',JSON.stringify(options),JSON.stringify(route),
      'P0=old Ms P7; P1=old Ms P8; exact twelve tetras; declared scratch only; program intact.');
  }
  assert.deepEqual([...pointerSlots].sort(),['P8','Y']);
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);
  console.log('PASS: observed/unobserved full core state:',firstDigest);
  console.log('NOT an intact-Ms operation: the upper pair is swapped; V marker and W:1F remain.');
}
if(require.main===module)main();
module.exports={check};
