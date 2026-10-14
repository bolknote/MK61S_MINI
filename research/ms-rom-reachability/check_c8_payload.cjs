#!/usr/bin/env node
'use strict';
// Regression cases derived from the 6E/61 decimal-counter semantics.
// They are NOT a search over arbitrary programs or key sequences.
const assert=require('node:assert/strict');
const {run,fullMsPages}=require('./probe_c8_payload.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');

const lane=(values,n)=>values.filter((_,i)=>i%3===n);
const hex=a=>a.map(v=>v.toString(16).toUpperCase()).join('');

function check(spec,options={}) {
  const result=run(spec.value,options),{report,tail,calc}=result;
  assert.deepEqual(report.reads.map(e=>e.slot),spec.slots);
  assert.deepEqual(report.reads.slice(1).map((e,i)=>e.command-report.reads[i].command),spec.gaps);
  assert.equal(report.primitives.length,spec.slots.length);
  assert.ok(report.primitives.every(ip=>ip==='C8'));
  assert.deepEqual(report.after,report.before,'all eight Ms numeric fields remain unchanged');
  assert.deepEqual(report.fullAfter,report.fullBefore,'all 56 Ms bytes remain unchanged');
  assert.deepEqual(report.programChanges,[{address:70,before:0,after:0x0E}],
    'only the ENTER deliberately programmed during preparation changes the listing');
  for(const e of tail.filter(e=>e.ip===0xC8)) {
    const after=tail.find(next=>next.command===e.command+1);
    assert.deepEqual(lane(after.r,1),lane(e.m,1),'all 14 source nibbles are really loaded');
  }
  const swaps=tail.filter(e=>e.ip===0xC9);
  assert.equal(swaps.length%2,0,'program packet fetches are paired exchanges');
  for(let i=0;i<swaps.length;i+=2) {
    const first=swaps[i],second=swaps[i+1];
    const after=tail.find(e=>e.command===second.command+1);
    assert.equal(second.slot,first.slot,'the same physical program packet returns');
    assert.deepEqual(lane(second.m,2),lane(first.r,1),
      'the temporary program packet retains the complete displaced R2 word');
    assert.deepEqual(lane(after.r,1),lane(first.r,1),
      'the second C9 restores the payload, not just the program');
  }
  const last=tail.findLast(e=>e.ip===0xC8);
  if(spec.retained) {
    assert.equal(report.retainedMantissa,spec.retained);
    assert.equal(report.retainedMantissa,hex(lane(last.m,1).slice(0,8)));
    assert.equal(report.display,'00 00 00 00');
    const beforeIdle=digest(calc);
    calc.runFrames(60);
    assert.equal(digest(calc),beforeIdle,'payload result is stable during a whole-ring idle wait');
    assert.equal(hex(Array.from({length:8},(_,i)=>calc.ik1302.r[7+3*i])),spec.retained);
  }
  console.log('PASS '+spec.name+' '+JSON.stringify(options)+': '+spec.slots.join(' -> ')
    +'; retained '+report.retainedMantissa+'; '+swaps.length/2+' verified C9 pairs.');
  return result;
}

function main() {
  const cases=[
    {name:'zero Ms baseline',value:null,slots:['W','P10','Y'],gaps:[20,20]},
    {name:'exponent 0',value:'1.2345678E0',slots:['W','P10','Y'],gaps:[20,20]},
    {name:'exponent 10',value:'1.2345678E10',slots:['W','V','P9','X'],gaps:[14,20,20]},
    {name:'exponent 20',value:'1.2345678E20',slots:['W','X1'],gaps:[8]},
    {name:'retain W A',value:'1.2345678E30',slots:['W'],gaps:[],retained:'87654321'},
    {name:'retain W B',value:'8.7654321E30',slots:['W'],gaps:[],retained:'12345678'},
    {name:'retain V',value:['1E10','8.7654321E30','333'],slots:['W','V'],gaps:[14],retained:'12345678'},
    {name:'retain U',value:['1E10','1E10','1.2345678E30'],slots:['W','V','U'],gaps:[14,14],retained:'87654321'},
  ];
  let recoveryInput;
  for(const spec of cases) {
    const result=check(spec);
    if(spec.name==='retain W B') recoveryInput=result;
  }
  for(const options of [{phaseOffset:1},{phaseOffset:2},{settleFrames:60}])
    check(cases.at(-1),options);
  console.log('PASS: 11 keyboard-only payload/route cases; no host state setters.');
  const {calc,report}=recoveryInput;
  const recovery=trace(calc,c=>c.pressSequence(['F','/-/']).runFrames(20));
  const repeatedReads=recovery.events.filter(e=>e.ip===0xEE&&e.raw==='600010000003');
  assert.ok(repeatedReads.length>100,'plain F AUTO repeatedly reprocesses the old nonstandard X');
  assert.deepEqual(recovery.primitives,[]);
  const state=digest(calc);
  calc.runFrames(9);
  assert.equal(digest(calc),state,'waiting alone stays in the same computation cycle');
  aligned(calc);
  assert.deepEqual(fullMsPages(calc),report.fullAfter);
  console.log('PASS recovery boundary: plain F AUTO causes '+repeatedReads.length+
    ' old-X reads in the observation window; state repeats after 9 idle frames. '+
    'This is NOT a usable return-to-calculation sequence.');
}

if(require.main===module) main();
module.exports={check,main};
