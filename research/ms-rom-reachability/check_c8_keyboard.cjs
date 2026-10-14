#!/usr/bin/env node
'use strict';
// Positive keyboard-only witness on the unchanged full IK1302/03/06 model.
// No state injection, ROM edit, user opcode 55/56, or extended-MK61S handler.
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const {MK61}=require('./paused_keyboard_state.cjs');
const {prepareCombined,finishCombined}=require('./check_ac_signature_keyboard.cjs');
const {run:probe}=require('./probe_combined_ac.cjs');

function digest(calc) {
  const state=[calc.ir2a,calc.ir2b,calc.ik1302,calc.ik1303,calc.ik1306].map(c=>({
    m:c.memory,r:c.r,st:c.stack,s:c.s,s1:c.s1,l:c.l,t:c.t,carry:c.carry,
    tick:c.tickIndex,input:c.input,output:c.output,keyX:c.keyX,keyY:c.keyY}));
  return createHash('sha256').update(JSON.stringify(state)).digest('hex');
}

function countWholeProtocol(options={}) {
  const calc=new MK61(),chip=calc.ik1302,original=chip.tick;
  const primitives=[];
  chip.tick=function() {
    if(this.tickIndex===0) {
      const ip=this.r[36]+16*this.r[39];
      if(ip===0xC7||ip===0xC8) primitives.push(ip);
    }
    return original.call(this);
  };
  try {
    prepareCombined({calc,counter:1});
    calc.runFrames(options.phaseOffset||0);
    finishCombined(calc,options);
  } finally {chip.tick=original;}
  return {calc,primitives};
}

function run() {
  const negative=probe({counter:0});
  assert.ok(negative.tail.some(e=>e.ip===0x37 && e.nextIp===0x25));
  assert.deepEqual(negative.result.primitives,[]);
  console.log('PASS: explicit P2=0 control takes 37->25 and does not enter C8.');

  const positive=probe({counter:1});
  const entries=positive.tail.filter(e=>e.ip===0xC8);
  assert.equal(entries.length,3);
  assert.ok(positive.tail.some(e=>e.ip===0x37 && e.nextIp===0x38));
  for(const before of entries) {
    const after=positive.tail.find(e=>e.command===before.command+1);
    const next=positive.tail.find(e=>e.command===before.command+2);
    const final=positive.tail.find(e=>e.command===before.command+3);
    assert.equal(before.nextIp,0x6E);
    assert.equal(after.ip,0x6E);
    assert.equal(next.ip,0x61);
    assert.ok([0x3A,0x63].includes(final.ip));
    assert.equal(before.r[38],4);
    assert.equal(before.r[26],9);
    assert.equal(before.r[25],before.r[31]);
    for(let i=1;i<42;i+=3) assert.equal(after.r[i],before.m[i],`C8 loads M[${i}]`);
    assert.equal(next.r[37]+16*next.r[40],before.m[37]+16*before.m[40]);
    assert.equal(final.r[37]+16*final.r[40],0x28);
  }
  console.log('PASS: P2=1 gives three actual C8 executions; all 14 loaded nibbles '+
    'and forced C8->6E->61 exits verified, including vector overwrite to 28.');

  const plain=prepareCombined({counter:1});
  finishCombined(plain);
  assert.equal(digest(plain),digest(positive.calc),'observer must not change calculator state');
  const whole=countWholeProtocol();
  assert.deepEqual(whole.primitives,[0xC8,0xC8,0xC8]);
  assert.equal(digest(whole.calc),digest(plain));
  console.log('PASS: full protocol has no earlier C7/C8; instrumented and uninstrumented '+
    'final chip states agree: '+digest(plain));

  // The three circulating frame phases and a longer idle wait are fixed
  // robustness controls, not a search over programs or keyboard sequences.
  for(const options of [{phaseOffset:1},{phaseOffset:2},{settleFrames:10}]) {
    const check=countWholeProtocol(options);
    assert.deepEqual(check.primitives,[0xC8,0xC8,0xC8],JSON.stringify(options));
    console.log('PASS: timing control '+JSON.stringify(options)+' also executes C8 three times.');
  }
  return positive;
}

if(require.main===module)run();
module.exports={run,digest,countWholeProtocol};
