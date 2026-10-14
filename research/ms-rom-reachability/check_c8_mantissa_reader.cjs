#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {readMantissa}=require('./probe_c8_mantissa_reader.cjs');
const {run}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {recover}=require('./check_c8_recovery.cjs');

let count=0;
function check(value,digits,options={}) {
  const result=readMantissa(value,options),{report}=result;
  assert.equal(report.mantissa,digits,JSON.stringify(value));
  for(let n=0;n<4;n++) {
    const pair=digits.slice(2*n,2*n+2);
    assert.equal(report.pairs[n].encoded,Number(pair)+1);
    assert.equal(report.pairs[n].decoded,pair);
  }
  assert.deepEqual(result.result.report.fullAfter,result.result.report.fullBefore);
  count++;
  console.log('PASS '+count+': '+JSON.stringify(value)+' -> '+
    report.pairs.map(p=>p.counter).join(' / ')+' -> '+report.mantissa);
  return result;
}

function differences(a,b,path='') {
  if(a===b) return [];
  if(a===null || b===null || typeof a!=='object' || typeof b!=='object')
    return [{path,a,b}];
  return [...new Set([...Object.keys(a),...Object.keys(b)])].flatMap(k=>
    differences(a[k],b[k],path?path+'.'+k:k));
}

function main() {
  // Twenty-five full keyboard preparations cover every possible two-digit
  // payload 00..99. All three fixture words are identical: boundary values
  // need not support the known writer's separate mixed-word shift protocol.
  const covered=new Set();
  for(let i=0;i<25;i++) {
    const pairs=[25+i,i,50+i,75+i];
    const digits=pairs.map(n=>String(n).padStart(2,'0')).join('');
    const value=digits[0]+'.'+digits.slice(1)+'E30';
    check([value,value,value],digits);
    pairs.forEach(n=>covered.add(n));
  }
  assert.deepEqual([...covered].sort((a,b)=>a-b),Array.from({length:100},(_,i)=>i));
  console.log('PASS: all 100 pairs, including decimal carries and 99 -> display -0.');

  const native=check('1.2345678E30','12345678',{fullTrace:true});
  const events=native.readout.events,shifts=events.filter(e=>e.ip===0x12);
  assert.equal(shifts.length,4,'one return-stack extraction per В/О');
  for(let n=0;n<shifts.length;n++) {
    const start=shifts[n];
    const c6=events.find(e=>e.command===start.command+1);
    const moved=events.find(e=>e.command===start.command+2);
    const incremented=events.find(e=>e.command===start.command+4);
    assert.equal(c6.ip,0xC6);assert.equal(moved.ip,0x38);
    assert.equal(incremented.ip,0x07);
    assert.equal(moved.r[31],start.r[25]);
    assert.equal(moved.r[34],start.r[28]);
    assert.equal(10*incremented.r[34]+incremented.r[31],
      native.report.pairs[n].encoded);
    for(let i=0;i<8;i++) assert.equal(moved.r[7+3*i],start.r[1+3*i]);
  }
  const plain=run('1.2345678E30');
  for(let i=0;i<4;i++) {
    plain.calc.press('В/О').runFrames(8);aligned(plain.calc);plain.calc.runFrames(60);
  }
  assert.equal(digest(native.calc),digest(plain.calc),'readout observer is non-mutating');
  console.log('PASS: actual 12/C6 shift and 06 increment on all four presses; observer equivalence.');
  recover(native.result);
  console.log('PASS: after all eight digits are read, the clean return still computes/stores 2+3=5.');

  // A full-machine causal control for every digit, including those which
  // were invisible in the earlier one-cycle, negative-exponent experiment.
  const control=check('1.1111111E30','11111111');
  for(let i=0;i<8;i++) {
    const digits=Array(8).fill('1');digits[i]='2';
    const value=digits[0]+'.'+digits.slice(1).join('')+'E30';
    const variant=check(value,digits.join(''));
    assert.deepEqual(differences(control.atFirstC8,variant.atFirstC8),
      [{path:'ik1302.m.'+(22-3*i),a:1,b:2}],
      'before first C8, only the selected Ms digit differs in the entire machine');
  }
  console.log('PASS: eight one-nibble causal controls, including all five chips and key pins.');

  check('-1.2345678E39','12345678');
  check('8.7654321E-71','87654321');
  check(['1E10','8.7654321E30','333'],'87654321');
  check(['1E10','1E10','1.2345678E30'],'12345678');
  check('1.2345678E30','12345678',{phaseOffset:1,readoutIdle:0});
  check('1.2345678E30','12345678',{phaseOffset:2,readoutIdle:0});
  check('1.2345678E30','12345678',{settleFrames:10,readoutIdle:20});
  for(const [value,digits] of [['9.9999900E30','99999900'],
                              ['1.0099999E30','10099999'],
                              ['1.0000000E30','10000000']])
    check([value,value,value],digits);
  console.log('PASS: '+count+' full keyboard-only eight-digit reads. No ROM/state injection, '+
    'no further C7/C8, no Ms/program changes, and every output stable for 60 idle frames.');
}

if(require.main===module) main();
module.exports={check,differences};
