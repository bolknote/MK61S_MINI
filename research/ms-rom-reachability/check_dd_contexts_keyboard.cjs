#!/usr/bin/env node
'use strict';
// All program and data setup is performed through keys; observation is read-only.
const assert = require('node:assert/strict');
const {run} = require('./probe_l0_keyboard.cjs');
for (const [counter,x] of [['1','12345673'],['1','1.2345673'],['2','12345673']]) {
  const r = run(counter,x);
  assert.deepEqual(r.primitives,[]);
  const reads = r.events.map((event,index)=>({event,index}))
    .filter(({event,index})=>event.ip===0xDD && r.events[index+1]?.ip===0xD6);
  assert.ok(reads.length>0);
  for (const {event,index} of reads) {
    assert.equal(event.sp[0],0x2F);
    assert.equal(event.vector,0xFF);
    assert.equal(event.r2,0);
    assert.equal(r.events[index+2].ip,0x2F);
    assert.equal(r.events[index+1].r38,4);
  }
  if (counter==='1') {
    const i = r.events.findIndex(e=>e.ip===0x07 && e.r38===4);
    assert.ok(i>=0);
    assert.equal(r.events[i].r2,0);
    assert.equal(r.events[i+1].ip,0x09);
  } else {
    const i = r.events.findIndex((e,i)=>e.ip===0xDD && r.events[i+1]?.ip===0xD4);
    assert.ok(i>=0);
    assert.equal(r.events[i].sp[0],0x26);
    assert.equal(r.events[i+2].ip,0x26);
  }
  console.log(`PASS: L0=${counter}, X=${x}: DD/D6 has return 2F, vector FF, `+
    `R2=0 and prepares selector 4; ${counter==='1'?'07 takes 09':'the write uses D4/26'}`);
}
console.log('PASS: 3 keyboard-only DD return-context cases, no C7/C8');
