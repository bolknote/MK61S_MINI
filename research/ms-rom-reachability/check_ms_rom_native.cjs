#!/usr/bin/env node
'use strict';
// Positive demonstrations use only calculator keys. Observers are read-only.
const assert = require('node:assert/strict');
const {MK61, trace, aligned} = require('./probe_ee_ring_source.cjs');
const {run: c8run} = require('./probe_c8_payload.cjs');
const allIps = Array.from({length:256}, (_,i)=>i);
const hex = n=>n.toString(16).toUpperCase().padStart(2,'0');

function ordinary(name, keys, wanted) {
  const calc = new MK61();
  for (const key of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[key] = ()=>{throw Error('Forbidden host setter: '+key);};
  calc.inputNumber('123',{clear:true});
  const result = trace(aligned(calc), c=>c.pressSequence(keys),
                       {extraIps:allIps,fullState:true});
  assert.ok(result.events.some(e=>e.ip===wanted), name);
  assert.ok(!result.events.some(e=>e.ip===0xC7 || e.ip===0xC8), name);
  if (name==='enter') {
    const first = result.events.findIndex(e=>e.ip===0xE7);
    const body = result.events.slice(first,first+5);
    assert.deepEqual(body.map(e=>e.ip),[0xE7,0xA8,0xA8,0xA8,0xA9]);
    assert.deepEqual(body.slice(0,4).map(e=>e.slot),['X','Y','Z','T']);
    assert.deepEqual(body.slice(0,4).map(e=>e.s1),[8,10,12,14]);
    for (let n=0;n<4;n++) for (let digit=0;digit<12;digit++)
      assert.equal(body[n+1].r[3*digit],body[n].m[1+3*digit]);
  }
  console.log('PASS:',name, result.events.filter(e=>
    [0xE7,0xA8,0xD4,0xD6].includes(e.ip)).map(e=>hex(e.ip)).join(' '));
}

ordinary('enter',['В↑'],0xE7);
ordinary('register store',['X→П','0'],0xD4);
ordinary('register recall',['П→X','0'],0xD6);

const result = c8run('8.7654321E-71');
const hits = result.tail.filter(e=>e.ip===0xC9);
assert.equal(hits.length,2,'one complete native C9 temporary-buffer pair');
assert.deepEqual(hits.map(e=>e.sp[0]),[0x67,0x06]);
assert.equal(hits[0].slot,hits[1].slot,'same physical program-lane page');
assert.equal((hits[1].command-hits[0].command)%15,0,'whole ring revolutions');
const lane = (a,n)=>a.filter((_,i)=>i%3===n);
assert.deepEqual(lane(hits[1].m,2),lane(hits[0].r,1),'parked word survived in M3');
assert.deepEqual(lane(hits[1].r,1),lane(hits[0].m,2),'second C9 writes the original program page');
const after = result.tail.find(e=>e.command===hits[1].command+1);
assert.deepEqual(lane(after.r,1),lane(hits[0].r,1),'second C9 restores the parked word');
// report.programChanges starts BEFORE finishCombined's programming keystrokes,
// not at C8. Its one 0E byte is therefore not a C9-pair preservation oracle.
assert.deepEqual(result.report.programChanges,[{address:70,before:0,after:0x0E}]);
assert.deepEqual(result.report.fullAfter,result.report.fullBefore);
assert.ok(!result.tail.some(e=>e.ip===0xBB || e.ip===0xBC));
console.log('PASS: C8 continuation calls C9 twice, returns to 67 then 06, '+
  'restores its program page and parked word, preserves Ms, and never calls BB/BC.');
console.log('No full K1/K2 is claimed by these keyboard tests.');
