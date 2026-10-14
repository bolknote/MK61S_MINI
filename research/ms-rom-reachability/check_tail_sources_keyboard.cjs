#!/usr/bin/env node
'use strict';
// Architectural source experiments, entirely through real reference keys.
// Hooks observe boundaries only. No chip/register/program-memory injection.
const assert=require('node:assert/strict');
const {MK61}=require('./paused_keyboard_state.cjs');
const {prepare}=require('./check_600_keyboard.cjs');
const hex=n=>n.toString(16).toUpperCase();

function observe(calc,action) {
  const chip=calc.ik1302,original=chip.tick;
  const rows=[],primitives=[];
  let previous=null;
  chip.tick=function() {
    if(this.tickIndex===0) {
      const ip=this.r[36]+16*this.r[39];
      rows.push({ip,previous,r:this.r.slice(),st:this.stack.slice(),
        raw:Array.from({length:12},(_,i)=>hex(this.memory[34-3*i])).join('')});
      if(ip===0xC7||ip===0xC8)primitives.push(rows.at(-1));
      previous=ip;
    }
    return original.call(this);
  };
  try {action(calc);} finally {chip.tick=original;}
  assert.deepEqual(primitives,[],'unexpected Ms entry: preserve the keyboard witness');
  return rows;
}

function prepare700() {
  return prepare(true,{input:'1E87',multiplier:'1.0000005E4'});
}

function finish700(calc) {
  calc.pressSequence(['В/О','С/П']).runFrames(12);
  assert.equal(calc.ik1302.r[2],12,'700 stops in the unusual programming-mode scanner');
  calc.pressSequence(['F','/-/']);
  assert.deepEqual(calc.ik1302.stack.slice(30,36),[0,15,0,7,9,5]);
  calc.press('В↑');
  calc.pressSequence(['БП','5','8']);
}

function prepareWrapped1200() {
  const calc=new MK61();
  calc.pressSequence(['F','ВП','F','*','F','*','F','*','F','*',
    'П→X','0','*','С/П','F','/-/','В/О']);
  assert.deepEqual(Array.from({length:7},(_,i)=>calc.readCommand(i)),
    [0x22,0x22,0x22,0x22,0x60,0x12,0x50]);
  calc.inputNumber('1.0000009',{clear:true}).pressSequence(['X→П','0']);
  calc.inputNumber('1E75',{clear:true});
  return calc;
}

function run() {
  const counter=new MK61();
  const counterRows=observe(counter,calc=>{
    calc.pressSequence(['БП','9','ВП']);
    assert.equal(calc.programCounter(),'9С'); // Cyrillic display C.
    calc.inputNumber('12345673',{clear:true}).pressSequence(['В↑','1','+']);
    assert.equal(calc.programCounter(),'9С');
  });
  assert.ok(counterRows.some(v=>v.ip===0x86 && v.previous===0x74 &&
    v.r[31]===12 && v.r[34]===9));
  assert.ok(counterRows.some(v=>v.ip===0x94 && v.previous===0x93 &&
    v.st[30]===12 && v.st[33]===9));
  assert.ok(counterRows.some(v=>v.ip===0x95 && v.previous===0x94 &&
    v.st[32]===12 && v.st[35]===9));
  assert.ok(counterRows.some(v=>v.ip===0xAC && v.r[31]===12 && v.r[34]===9));
  assert.ok(counterRows.filter(v=>v.ip===0xAC).every(v=>v.st[32]===0 && v.st[35]===0));
  assert.deepEqual(counter.ik1302.stack.slice(30,36),[15,0,0,15,0,0]);
  console.log('PASS: БП 9 ВП gives genuine PC9C; 74 copies it and 93/94 '+
    'put C/9 into saved ST. Ordinary cleanup clears it before the next AC.');

  const seven=prepare700();
  const sevenRows=observe(seven,finish700);
  assert.ok(sevenRows.some(v=>v.ip===0xEE && v.raw==='700010000005'));
  assert.ok(sevenRows.some(v=>v.ip===0xAC && v.r[31]===8 && v.r[34]===5 &&
    v.r[1]===5 && v.st[32]===0 && v.st[35]===5));
  assert.equal(seven.programCounter(),'58');
  console.log('PASS: real 700010000005, F АВТ, В↑, БП58 gives AC with '+
    'PC58/R1=5, but the persistent tail is 0/5, not the required high/9.');

  const wrap=prepareWrapped1200();
  const wrapRows=observe(wrap,calc=>calc.pressSequence(['В/О','С/П']).runFrames(12));
  assert.ok(wrapRows.some(v=>v.ip===0xEE && v.raw==='600010000000'));
  assert.ok(wrapRows.some(v=>v.ip===0xEE && v.raw==='200010000000'));
  assert.ok(wrapRows.some(v=>v.ip===0xEE && v.raw==='200010000009'));
  assert.ok(wrapRows.filter(v=>v.ip===0xEE).every(v=>v.raw[0]!=='C'));
  console.log('PASS: four squares from 1E75 wrap 600 to 200, not C00; '+
    'the proposed order-1200 source is absent in this concrete construction.');
  return {counterRows,sevenRows,wrapRows};
}

if(require.main===module)run();
module.exports={run,observe,prepare700,finish700,prepareWrapped1200};
