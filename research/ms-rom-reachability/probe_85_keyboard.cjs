#!/usr/bin/env node
'use strict';
// Keyboard-only setup. The observer reads chip fields without modifying them.
const assert = require('node:assert/strict');
const path = require('node:path');
const {MK61} = require(path.join(process.env.MK61_REFERENCE_ROOT ||
  path.resolve(__dirname,'../../..','MK-61'),'tests/emulator/mk61.cjs'));
const hex = n => n.toString(16).toUpperCase().padStart(2,'0');
const writers38 = new Set([0x1F,0x59,0x5C,0x5F,0x6C,0x7C,0x85,0xB3,0xCD,0xDD,0xDE,0xE6]);
const cases = [
  {label:'first digit', setup:[], key:'4', next:0x88, flag:0, count:1, lift:0},
  {label:'continuing mantissa', setup:['1'], key:'4', next:0x89, flag:0, count:2, lift:0},
  {label:'after decimal point', setup:['1',','], key:'4', next:0x89, flag:15, count:2, lift:0},
  {label:'after addition', setup:['3','3','В↑','2','2','В↑','1','1','В↑','2','В↑','3','+'],
    key:'4', next:0x87, flag:0, count:1, lift:15, stack:['4,','5,','11,','22,']},
  {label:'after ENTER', setup:['2','В↑'], key:'4', next:0x88, flag:0, count:1, lift:0, y:'2,'},
  {label:'ninth digit rejected', setup:'12345678'.split(''), key:'9', absent:true,
    rejectCount8:true, display:'12345678,'},
  {label:'exponent entry', setup:['1','ВП'], key:'4', absent:true},
];

function run(test) {
  const calc=new MK61();
  calc.pressSequence(test.setup);
  const chip=calc.ik1302, original=chip.tick, history=[], hits=[], primitives=[];
  let entry=null;
  chip.tick=function(){
    if(this.tickIndex===0){
      const ip=this.r[36]+16*this.r[39];
      entry={ip,r26:this.r[26],r30:this.r[30],r35:this.r[35],r38:this.r[38],
        r41:this.r[41],s:this.s,s1:this.s1};
      history.push(entry);
      if(ip===0x85)hits.push({index:history.length-1,entry});
      if(ip===0xC7||ip===0xC8)primitives.push(ip);
    }
    const result=original.call(this);
    if(this.tickIndex===0){
      entry.next=this.r[36]+16*this.r[39];
      entry.afterR38=this.r[38];
    }
    return result;
  };
  try {calc.press(test.key);} finally {chip.tick=original;}
  const stack=['x','y','z','t'].map(r=>calc.readRegister(r));
  return {label:test.label,display:calc.displayText(),y:stack[1],stack,primitives,
    gates82:history.filter(e=>e.ip===0x82),
    hits:hits.map(({index,entry})=>{
      const overwrite=history.slice(index+1).find(e=>writers38.has(e.ip));
      return {entry,overwrite,entryRoute:history.slice(Math.max(0,index-12),index+1).map(e=>e.ip),
        exitRoute:history.slice(index,Math.min(history.length,index+35)).map(e=>e.ip)};
    })};
}

module.exports={run,cases};
if(require.main===module){
  const observed=new Set();
  for(const test of cases){
    const report=run(test);
    assert.deepEqual(report.primitives,[]);
    if(test.absent)assert.equal(report.hits.length,0,test.label);
    else{
      assert.equal(report.hits.length,1,test.label);
      const hit=report.hits[0], e=hit.entry;
      assert.equal(e.r30,4);
      assert.equal(e.r35,test.flag);
      assert.equal(e.r26,test.count);
      assert.equal(e.r41,test.lift);
      assert.equal(e.s,test.lift);
      assert.equal(e.next,test.next);
      assert.equal(e.afterR38,test.flag);
      assert.equal(hit.overwrite.ip,0xE6);
      assert.ok([12,13].includes(hit.overwrite.afterR38));
      observed.add(e.next);
    }
    if(test.y)assert.equal(report.y,test.y);
    if(test.stack)assert.deepEqual(report.stack,test.stack);
    if(test.rejectCount8)assert.ok(report.gates82.some(e=>e.r26===8 && e.next===0xBD));
    if(test.display)assert.equal(report.display,test.display);
    if(process.argv.includes('--json'))console.log(JSON.stringify(report));
    else console.log(`PASS: ${test.label}: ${report.hits.length ?
      report.hits.map(h=>`85->${hex(h.entry.next)}, R35=${hex(h.entry.r35)}, next R38 writer E6=${hex(h.overwrite.afterR38)}`).join('; ') :
      'no 85 entry'}`);
  }
  assert.deepEqual([...observed].sort(),[0x87,0x88,0x89]);
  console.log(`PASS: ${cases.length} keyboard-only cases cover every exit of 85; no C7/C8`);
}
