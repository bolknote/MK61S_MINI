#!/usr/bin/env node
'use strict';
// Explicitly rejected continuations, not recipes for a recovered operation.
const assert=require('node:assert/strict');
const p=require('./probe_ms_two_markers.cjs');
const five=require('./probe_ms_read5_restore.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const marker='0000F0000000';
const shifted=p.run({shifts:3,reads:true});
const es=shifted.traced.events;
const store=es.find(e=>e.stage==='read-1'&&e.ip===0xD4);
assert.equal(store.slot,'P8','store 41 is misaddressed to ordinary P5, not P1');
const at=es.findIndex(e=>e.stage==='shift-2'&&e.ip===0xE7&&e.slot==='P8');
assert.ok(at>=0);const b=checkSwapBlock(shifted,at,4);
assert.deepEqual(b.body.map(e=>e.slot),['P8','P9','P10','marker']);
assert.equal(b.body[0].ring.marker[22],15);assert.equal(b.after.ring.marker[22],0,
  'the attempted third shift erases the genuine ring marker');
assert.equal(shifted.after.W.slice(2),marker,'the intended move to Q never occurred');
console.log('PASS: negative control: continuing with P8 through the W marker misaddresses P1 and erases the real marker.');
const zero=p.run({shifts:1,reads:true,tailActions:[['erase-v',['П→X','2']]],cleanup:true});
assert.equal(zero.beforeRegisters[2],'000000000000');assert.equal(zero.after.V.slice(2),marker);
assert.ok(!zero.traced.events.some(e=>e.stage==='erase-v'&&e.ip===0xE7&&e.slot==='V'));
console.log('PASS: negative control: zero P2 is not an eraser; the internal V marker survives.');
const cleanup=p.run({shifts:1,reads:true,cleanup:true});
assert.equal(cleanup.after.V.slice(2),marker);
assert.notEqual(cleanup.after.W,cleanup.before.U,'ordinary cleanup also damages the following control header');
console.log('PASS: negative control: four ordinary zero recalls alone remove visible markers, not the internal V marker.');
const negative=five.run({phaseOffset:1,values:['111','222','333','-1.2345678E-42']});
assert.notDeepEqual(negative.after,negative.before);
const stage=negative.traced.events.find(e=>e.stage==='prepare-eraser');
assert.equal(p.raw(stage.ring.Q),negative.before.W.slice(2),
  'Q was already lost by the existing four-word backup on the out-of-domain U');
console.log('PASS: negative control: negative-exponent U breaks the full composition; changed Ms:',
  JSON.stringify(Object.fromEntries(Object.keys(negative.before).filter(n=>negative.before[n]!==negative.after[n]).map(n=>[n,{before:negative.before[n],after:negative.after[n]}]))));
console.log('No universal impossibility is claimed: these are boundaries of the tested sequences.');
