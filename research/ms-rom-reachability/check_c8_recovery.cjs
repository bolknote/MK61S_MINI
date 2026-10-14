#!/usr/bin/env node
'use strict';
// A clean return to ordinary calculation, NOT yet a user-visible Ms read.
const assert=require('node:assert/strict');
const {run,fullMsPages}=require('./probe_c8_payload.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');

const retained=calc=>Array.from({length:8},(_,i)=>calc.ik1302.r[7+3*i]);
const program=calc=>Array.from({length:105},(_,i)=>calc.readCommand(i));

function recover(result,{idleFrames=4}={}) {
  const {calc,report}=result;
  aligned(calc);
  const digits=retained(calc),listing=program(calc);
  const checkpoints=[];
  const press=keys=>{
    for(const key of keys) calc.press(key).runFrames(idleFrames);
    aligned(calc);
  };
  const check=label=>{
    assert.deepEqual(retained(calc),digits,label+': all eight C8 digits survive');
    assert.deepEqual(fullMsPages(calc),report.fullAfter,label+': Ms unchanged');
    assert.deepEqual(program(calc),listing,label+': program unchanged');
    checkpoints.push({label,display:calc.displayText(),
      x:calc.readRegister('x',{syncPhase:false}),
      digits:digits.map(n=>n.toString(16)).join('')});
  };
  const observed=trace(calc,()=>{
    press(['П→X','0']);
    assert.equal(calc.readRegister('x',{syncPhase:false}),'10000,005');
    assert.equal(calc.displayText(),'10000,005');
    check('recall P0 replaces the old X');
    press(['F','/-/']);
    assert.equal(calc.readRegister('x',{syncPhase:false}),'10000,005');
    check('F AUTO now completes');
    press(['Сx','2','В↑','3','+','X→П','8']);
    assert.equal(rawMemoryRegister(calc,8),'000050000000');
    assert.equal(calc.readRegister('x',{syncPhase:false}),'5,');
    assert.equal(calc.displayText(),'5,');
    check('ordinary 2+3 is stored in P8');
  });
  assert.deepEqual(observed.primitives,[],'recovery does not call another C7/C8');
  const beforeWait=digest(calc);
  calc.runFrames(60);
  assert.equal(digest(calc),beforeWait,'ordinary scanner is stable');
  check('60 additional idle frames');
  return {checkpoints,observed};
}

function main() {
  const cases=[
    '1.0234567E30',
    '8.7654321E30',
    ['1E10','8.7654321E30','333'],
    ['1E10','1E10','1.2345678E30'],
  ];
  for(const value of cases) {
    const result=run(value);
    const {checkpoints}=recover(result);
    console.log('PASS recovery '+JSON.stringify(value)+': '+JSON.stringify(checkpoints));
  }
  const slow=run(cases[0],{phaseOffset:2});
  recover(slow,{idleFrames:12});
  console.log('PASS: 5 keyboard-only clean-return cases. The visible 5 is an '+
    'arithmetic control, NOT the Ms payload; all eight payload digits remain internal.');
}

if(require.main===module) main();
module.exports={recover,retained};
