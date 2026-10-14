#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const calc=aligned(new MK61());
for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
  calc[name]=()=>{throw new Error('Forbidden state setter: '+name);};
const r=trace(calc,c=>c.pressSequence(['Сx','K','Сx','K','8']).runFrames(8),
  {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true});
aligned(calc);
const word=a=>Array.from({length:12},(_,i)=>a[34-3*i].toString(16).toUpperCase()).join('');
assert.equal(word(calc.ik1303.memory),'9990FFFFFFF0');
assert.equal(word(calc.ir2b.memory.slice(126,168)),'9990FFFFFFF0');
assert.equal(word(calc.ik1306.memory),'00008FFFFFFF');
const created=r.writes.filter(w=>w.nibble===22&&w.before!==15&&w.value===15);
assert.ok(created.length>=2);
assert.deepEqual(created.map(w=>[w.chip,w.ip,w.slot,w.before]),
  [[5,0xFF,'X',8],[3,0xE7,'T',0]]);
assert.deepEqual(r.primitives,[]);
console.log('PASS: Cx K INV K fractional-part creates 9990FFFFFFF0 natively; '
  +'first false leading F is IK1306:FF writing X, then IK1302:E7 writes T.');
console.log('The source 00008FFFFFFF has leading digit 8, so logical inversion alone is not this E5 marker.');
