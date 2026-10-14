#!/usr/bin/env node
'use strict';
// Native keys only. Positive readout cases and explicit limits of the recipe.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {run,recover,registers,program}=require('./probe_a8_ms_readout.cjs');
const {prepare,finish}=require('./probe_a8_marker_route.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const provedRoute=fs.readFileSync(path.join(__dirname,'check_a8_readout_control.py'),'utf8')
  .match(/ROUTE='''([\s\S]*?)'''/)[1].trim().split(/\s+/).map(s=>parseInt(s,16));
const A=e=>Array.from({length:12},(_,i)=>e.r[3*i]);
const numeric=m=>Array.from({length:12},(_,i)=>m[1+3*i]);
const raw=a=>a.slice().reverse().map(v=>v.toString(16).toUpperCase()).join('');
const msRing=ring=>Object.fromEntries(['U','V','W','Q','P7','P8','P9','P10'].map(s=>
  [s,Array.from({length:14},(_,i)=>ring[s][40-3*i])]));

function checkSwapBlock(result,at,count) {
  const es=result.traced.events,body=es.slice(at,at+count),after=es[at+count];
  assert.deepEqual(body.map(e=>e.ip),[0xE7,...Array(count-1).fill(0xA8)]);
  assert.ok(after.ring,'snapshot immediately after the block');
  const expected=structuredClone(body[0].ring);
  let carried=A(body[0]);
  for(const e of body) {
    assert.deepEqual(A(e),carried);
    const displaced=numeric(expected[e.slot]);
    for(let i=0;i<12;i++) expected[e.slot][1+3*i]=carried[i];
    carried=displaced;
  }
  assert.deepEqual(after.ring,expected,'all 630 ring tetras, including all service/program lanes');
  assert.deepEqual(A(after),carried,'all twelve displaced tetras survive the last swap');
  const writes=result.traced.writes.filter(w=>w.command>=body[0].command&&w.command<after.command);
  assert.equal(writes.length,12*count,'all-chip write count');
  assert.ok(writes.every(w=>w.chip===3));
  assert.deepEqual(writes.map(w=>[w.slot,w.nibble]),body.flatMap(e=>
    Array.from({length:12},(_,i)=>[e.slot,1+3*i])));
  return {body,after};
}

function main() {
const cases=[{}, {phaseOffset:1}, {phaseOffset:2}, {settleFrames:12},
  {values:['111','222','-8.7654321E17','12345678']},
  {values:['111','222','333','-444']},
  {values:['111','222','-8.7654321E-17','1.2345678E42']}];
let firstDigest,firstOptions;
for(const options of cases) {
  const r=run(options),es=r.traced.events;
  firstDigest??=digest(r.calc);firstOptions??=r.options;
  const u=r.before.U.slice(2),v=r.before.V.slice(2);
  assert.ok(!r.beforeRegisters.includes(u)&&!r.beforeRegisters.includes(v),
    'the requested words are not leftovers in ordinary registers');
  assert.equal(r.afterRegisters[9],u,'all twelve tetras U -> P9');
  assert.equal(r.afterRegisters[2],v,'all twelve tetras V -> P2');
  for(let i=0;i<15;i++) if(i!==2&&i!==9)
    assert.equal(r.afterRegisters[i],r.beforeRegisters[i],'unrelated ordinary register P'+i+' preserved');
  assert.deepEqual(r.afterProgram,r.beforeProgram,'all 105 program steps preserved');
  assert.deepEqual(r.traced.primitives,[],'no C7 or C8 address entries');
  assert.equal(es.filter(e=>e.ip===0xC9).length,0,'program-lane swap is not entered at all');
  const uGuard=es.find(e=>e.stage==='lift-marker-1'&&e.ip===0x9C&&e.slot==='U');
  if(uGuard) {assert.equal(uGuard.m[34],0);assert.equal(uGuard.nextIp,0x9D);}
  const at=es.findIndex(e=>e.stage==='recall'&&e.ip===0xE7&&e.slot==='U'&&e.s1===7);
  assert.ok(at>=0,'one-word native E7 entry at U');
  assert.equal(es[at].raw,u);assert.deepEqual(A(es[at]),Array(12).fill(0));
  const single=checkSwapBlock(r,at,1);
  assert.equal(single.after.ip,0xAD);
  const uLiftAt=es.findIndex((e,i)=>i>at&&e.ip===0xE7&&e.slot==='X'&&e.s1===8);
  const uLift=checkSwapBlock(r,uLiftAt,4);
  assert.deepEqual(uLift.body.map(e=>e.slot),['X','Y','Z','T']);
  assert.equal(raw(A(uLift.body[0])),u,'U really reaches X through the full-word accumulator');
  assert.equal(uLift.after.ring.T[22],15,'the false marker has only moved to T');
  assert.equal(uLift.body[3].m[22],0,'the displaced old T now has a zero leading digit');
  const beforeRecovery=es.find(e=>e.stage==='read-v-remove-marker');
  assert.equal(beforeRecovery.ring.T[22],15);
  const vReadAt=es.findIndex(e=>e.stage==='read-v-remove-marker'&&e.ip===0xEE&&e.slot==='V');
  assert.ok(vReadAt>=0);assert.equal(es[vReadAt].raw,v);
  const vLiftAt=es.findIndex((e,i)=>i>vReadAt&&e.ip===0xE7&&e.slot==='X'&&e.s1===8);
  const vLift=checkSwapBlock(r,vLiftAt,4);
  assert.deepEqual(vLift.body.map(e=>e.slot),['X','Y','Z','T']);
  assert.equal(raw(A(vLift.body[0])),v,'V is not reconstructed from display digits');
  assert.equal(raw(numeric(vLift.after.ring.X)),v);
  assert.equal(raw(numeric(vLift.after.ring.Y)),u);
  for(const slot of ['X','Y','Z','T']) assert.notEqual(vLift.after.ring[slot][22],15);
  const saveV=es.find(e=>e.stage==='save-v'),done=es.find(e=>e.stage==='done');
  assert.deepEqual(msRing(done.ring),msRing(saveV.ring),
    'after removing the false marker, saving/cleanup does not alter any of the 112 Ms tetras');
  const relevantBE=es.find(e=>e.ip===0xBE&&e.command>uLift.after.command&&e.stage==='recall');
  assert.ok(relevantBE);assert.equal(relevantBE.r[23],0);assert.equal(relevantBE.nextIp,0xB0);
  if(options.values===undefined) {
    const acAt=es.findLastIndex((e,i)=>i<at&&e.ip===0xAC);
    const beAt=es.indexOf(relevantBE);
    const actualRoute=es.slice(acAt,beAt+1)
      .filter((e,i,rows)=>!(e.ip===0xE5&&rows[i-1]?.ip===0xE5)).map(e=>e.ip);
    assert.deepEqual(actualRoute,provedRoute,'same connected 138-command route as the symbolic provenance proof');
  }
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,','ordinary arithmetic works after readout');
  aligned(r.calc);
  assert.deepEqual(registers(r.calc),r.afterRegisters,'arithmetic preserves saved U/V and other registers');
  assert.deepEqual(program(r.calc),r.beforeProgram);
  assert.deepEqual(fullMsPages(r.calc),r.after,'arithmetic does not shift Ms again');
  console.log('PASS:',JSON.stringify(options),'U -> P9, V -> P2, 12/48/48 writes and all 630 tetras; no C9; program intact; 2 ENTER 3 + = 5.');
}
const plain=prepare(firstOptions);finish(plain,firstOptions);recover(plain,firstOptions);plain.runFrames(3);aligned(plain);
assert.equal(digest(plain),firstDigest,'observers do not affect the complete reference state');
console.log('PASS: observed/unobserved full states agree:',firstDigest);

for(const clearKey of ['Сx','5']) {
  const r=run({clearKey});
  assert.equal(r.afterRegisters[9],r.before.U.slice(2));
  assert.equal(r.afterRegisters[2],r.before.V.slice(2));
  const first=r.traced.events.find(e=>e.ip===0xBE&&e.stage==='recall');
  assert.equal(first.r[23],clearKey==='Сx'?8:1);assert.equal(first.nextIp,0x63);
  assert.ok(r.traced.events.some(e=>e.ip===0xC9));
  assert.notDeepEqual(r.afterProgram,r.beforeProgram,'correct visible readout alone was not enough');
  console.log('PASS: negative control',clearKey,'reads U/V but restores nonzero R23 and corrupts the program.');
}
const direct=run({skipLastX:true});
assert.notEqual(direct.afterRegisters[9],direct.before.U.slice(2),
  'saving the visible U without removing the false marker does not save U');
console.log('PASS: negative control: direct X -> P9 without F ENTER saves the wrong physical word.');
for(const value of ['-1.2345678E-42','1.2345678E-42']) {
  const negativeU=run({values:['111','222','333',value]});
  assert.notEqual(negativeU.afterRegisters[9],negativeU.before.U.slice(2));
  const guard=negativeU.traced.events.find(e=>e.stage==='lift-marker-1'&&e.ip===0x9C&&e.slot==='U');
  assert.ok(guard);assert.equal(guard.m[34],9);assert.equal(guard.nextIp,0x9E);
  negativeU.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.notEqual(negativeU.calc.displayText(),'5,');
  console.log('PASS: domain counterexample:',value,'makes 9C accept U as a false control word; readout fails.');
}
console.log('NOT K1: finite two-word readout with a recovered exit on the tested domain; U is cleared, other Ms words shift, no inverse eight-word exchange.');
}
if(require.main===module) main();
module.exports={checkSwapBlock};
