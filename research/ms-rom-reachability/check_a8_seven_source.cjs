#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {run,prepare,finish}=require('./probe_a8_seven_source.cjs');
const {aligned,trace}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const referenceRoute=fs.readFileSync(path.join(__dirname,'check_a8_single_route.py'),'utf8')
  .match(/ROUTE='''([\s\S]*?)'''/)[1].trim().split(/\s+/).map(s=>parseInt(s,16));
const numeric=page=>Array.from({length:12},(_,i)=>page[1+3*i]);
const accumulator=event=>Array.from({length:12},(_,i)=>event.r[3*i]);
const cases=[{}, {payloadRegister:6}, {phaseOffset:1}, {phaseOffset:2},
  {settleFrames:12}, {payloadLowDigit:7},
  {values:['-1.2345678E-42','8.7654321E17','-23456789','34567891']}];
let firstDigest;
for(const options of cases) {
  const result=run(options);firstDigest??=digest(result.calc);
  const stages=Object.fromEntries(result.stages.map(s=>[s.label,s]));
  assert.equal(stages['seed-seven'].tail[4],7,'register-7 recall leaves ST34=7');
  assert.equal(stages['save-seven'].tail[5],7,'F AVT transfers that 7 to ST35');
  assert.equal(stages.address.pc,0xE0);
  assert.equal(stages.address.tail[5],7);
  const seed=result.traced.events.find(e=>e.stage==='seed-seven'&&e.ip===0xAC);
  assert.equal(seed.r[35],7,'the recall operand is still in R35 at AC');
  const seedAA=result.traced.events.find(e=>e.stage==='seed-seven'&&e.ip===0xAA);
  assert.deepEqual([seedAA.r[30],seedAA.r[33]],[7,6],'decoded native recall opcode 67');
  assert.equal(result.singles.length,1);
  const s=result.singles[0];
  assert.equal(s.ac.pc,0xE0);assert.equal(s.ac.st35,7);
  assert.deepEqual(s.route.map(e=>e.ip),referenceRoute,'same connected 91-word ROM path');
  assert.deepEqual([s.route[5].m[34],s.route[69].m[34]],[6,6]);
  assert.deepEqual(s.ee.sp,[0xA8,0x93,0xE5]);
  assert.deepEqual(s.swap.sp,[0x93,0xE5,0xA8]);
  assert.equal(s.swap.nextIp,0xA9);assert.equal(s.exit.nextIp,0x93);
  assert.equal(s.swap.s1,14);assert.equal(s.exit.s1,0);
  assert.deepEqual([s.ee.slot,s.swap.slot],['X1','X']);
  assert.deepEqual(accumulator(s.swap),numeric(s.ee.m));
  assert.deepEqual(accumulator(s.exit),numeric(s.swap.m));
  assert.deepEqual(accumulator(s.after).slice(0,10),numeric(s.swap.m).slice(0,10));
  assert.equal(s.after.r[30],0);assert.equal(s.after.r[33],14);
  assert.equal(s.writes.length,12,'twelve writes across all THREE processors');
  assert.ok(s.writes.every(w=>w.chip===3&&w.ip===0xA8&&w.slot==='X'));
  assert.deepEqual(s.writes.map(w=>w.nibble),Array.from({length:12},(_,i)=>1+3*i));
  const expected=structuredClone(s.swap.ring);
  for(let i=0;i<12;i++) expected.X[1+3*i]=s.ee.m[1+3*i];
  assert.deepEqual(s.exit.ring,expected,'all 630 physical ring tetras after A8');
  const at=result.traced.events.findIndex(e=>e.command===s.swap.command);
  const marker=result.traced.events[at-3],control=result.traced.events[at-2];
  assert.equal(marker.ip,0xE5);assert.equal(marker.m[22],15);
  assert.equal(marker.slot,'marker');assert.equal(control.ip,0xE6);
  assert.equal(control.slot,'control');
  assert.deepEqual(result.beforeMs,result.afterMs,'all 112 Ms tetras unchanged');
  assert.deepEqual(result.traced.primitives,[],'no C7/C8 address entry in this construction');
  const reg=options.payloadRegister??4;
  assert.equal(rawMemoryRegister(result.calc,reg),'60001000000'+(options.payloadLowDigit??1));
  assert.equal(rawMemoryRegister(result.calc,7),'700010000005');
  if(reg===6) {
    assert.equal(stages.recall.ip,0xE6);assert.equal(stages.recall.s1,6);
    assert.ok(result.traced.events.slice(-560).every(e=>e.ip===0xE6));
  } else {
    assert.equal(stages.recall.ip,0x35);
    if(options.payloadLowDigit===7) {
      assert.equal(stages.recall.r2,0);assert.equal(result.calc.displayText(),'50 47 08');
    } else {
      assert.equal(stages.recall.r2,8);assert.equal(result.calc.displayText(),'0,');
    }
    result.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(4);
    assert.equal(result.calc.displayText(),'5,','native key processing works after return');
  }
  console.log('PASS:',JSON.stringify(options),'native ST35=7/PC=E0; connected single A8; '
    +'X1 -> X, all 630 tetras checked; '+(reg===6?'E6-loop control.':'returns to scanner.'));
}
const plain=prepare();finish(plain);aligned(plain);
assert.equal(digest(plain),firstDigest,'observers do not change complete reference state');
console.log('PASS: observed/unobserved complete states agree:',digest(plain));
plain.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(4);
assert.equal(plain.displayText(),'5,');
console.log('PASS: returned calculator accepts 2 ENTER 3 + and displays 5.');
const msBeforeRepeat=fullMsPages(aligned(plain));
const repeated=trace(plain,calc=>{
  for(const keys of [['Сx'],['П→X','7'],['F','/-/'],['Сx'],['БП','В↑','0'],['П→X','4']])
    calc.pressSequence(keys).runFrames(8);
},{extraIps:Array.from({length:256},(_,i)=>i),fullState:true});
const repeatedIndices=repeated.events.map((e,i,es)=>
  e.ip===0xA8&&e.s1===14&&es[i-1]?.ip===0xEE?i:-1).filter(i=>i>=0);
assert.equal(repeatedIndices.length,1,'second call without rebuilding either constant');
const repeatIndex=repeatedIndices[0];
const repeatAC=repeated.events.findLastIndex((e,i)=>i<repeatIndex&&e.ip===0xAC);
assert.deepEqual(repeated.events.slice(repeatAC,repeatIndex+2)
  .filter((e,i,es)=>!(e.ip===0xE5&&es[i-1]?.ip===0xE5)).map(e=>e.ip),referenceRoute);
assert.equal(plain.displayText(),'0,');
assert.deepEqual(fullMsPages(aligned(plain)),msBeforeRepeat);
console.log('PASS: the same short call works again after ordinary arithmetic; constants need no rebuild, Ms unchanged.');
console.log('NOT K1: this construction copies X1 to X, leaves Ms unchanged, and A9 alters the displaced exponent.');
