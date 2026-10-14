#!/usr/bin/env node
'use strict';
// All program/data setup uses real keys; tick wrapping only observes.
const assert = require('node:assert/strict');
const {run} = require('./probe_l0_keyboard.cjs');
let count = 0;
for(const [x,selector] of [
  ['12345673',4], ['1.2345673',4], ['-12345673',4], ['12345678',9]
]) {
  const report=run('1',x);
  assert.deepEqual(report.primitives,[]);
  assert.equal(report.snapshot.r[2],0);
  assert.equal(report.snapshot.r[32],13);
  assert.equal(report.snapshot.r[35],5);
  const index=report.events.findIndex(e=>e.ip===0x07 && e.r38===selector);
  assert.ok(index>=0,`${x}: loop completion must reach 07 with R38=${selector}`);
  assert.equal(report.events[index].r2,0);
  assert.equal(report.events[index+1].ip,0x09);
  assert.equal(report.pc,'03');
  count++;
  console.log(`PASS: X=${x}, L0 counter=1: DD selector ${selector}, then 07->09; no C7/C8`);
}
for(const counter of ['0','2']) {
  const report=run(counter);
  assert.deepEqual(report.primitives,[]);
  const index=report.events.findIndex(e=>e.ip===0x37);
  assert.ok(index>=0);
  assert.equal(report.events[index+1].ip,0x25);
  assert.equal(report.pc,'04');
  count++;
  console.log(`PASS: L0 counter=${counter}: nonzero branch 37->25; no C7/C8`);
}
const large=run('12345674');
assert.deepEqual(large.primitives,[]);
const written=large.events.find(e=>e.ip===0xD4);
assert.ok(written);
assert.equal(written.r38,4);
const decision=large.events.findIndex(e=>e.ip===0x28);
assert.ok(decision>=0);
assert.equal(large.events[decision].r26,0);
assert.equal(large.events[decision+1].ip,0x2A);
count++;
console.log('PASS: L0 counter=12345674 also prepares R38=4, but takes 28->2A, not 7E');
const manual=run('1','12345673','manual');
assert.equal(manual.snapshot,null);
assert.equal(manual.pc,'00');
assert.ok(!manual.observed.includes(0xDD));
assert.deepEqual(manual.primitives,[]);
count++;
console.log('PASS: direct F П→X in calculation mode does not execute this L0 body');
console.log(`PASS: ${count} keyboard-only L0 cases`);
