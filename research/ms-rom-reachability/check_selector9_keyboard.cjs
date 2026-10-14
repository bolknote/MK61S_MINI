#!/usr/bin/env node
'use strict';
const assert = require('node:assert/strict');
const {run} = require('./probe_l0_keyboard.cjs');

for (const x of ['12345678','1.2345678E13']) {
  const result = run('1',x);
  assert.deepEqual(result.primitives,[]);
  const dd = result.events.findIndex(e => e.ip===0xDD && e.r0===8);
  assert.ok(dd>=0);
  assert.equal(result.events[dd+1].ip,0xD6);
  assert.equal(result.events[dd+1].r38,9);
  if (x.includes('E13')) assert.equal(result.events[dd].r27,3);
  const fill = result.events.findIndex((e,i) => i>dd && e.ip===0x38 && e.r38===9);
  const gate = result.events.findIndex((e,i) => i>fill && e.ip===0x07 && e.r38===9);
  assert.ok(fill>dd && gate>fill);
  assert.deepEqual([result.events[gate].r2,result.events[gate].r26,
    result.events[gate].r27], [0,0,15]);
  assert.equal(result.events[gate+1].ip,0x09);
  console.log(`PASS: P0=1, X=${x}: DD prepares 9; 38 replaces the useful `+
    'R27 digit by F before 07, whose low R2 chooses 09. No C7/C8.');
}
console.log('PASS: two keyboard-only selector9/fill-digit cases.');
