#!/usr/bin/env node
'use strict';
const assert = require('node:assert/strict');
const {tracePaused} = require('./probe_paused_paths.cjs');
const scanner = new Set([0x35,0x45,0x65,0x7B,0x83,0x8A,0xB5,0xB7,0xC5]);

for (const keys of [['K','1'], ['K','БП','ВП'], ['F','ВП'],
    ['F','ВП','K','1'], ['F','ВП','K','2'],
    ['Сx','1','ВП','1','3','F','ВП']]) {
  const result = tracePaused(keys);
  assert.deepEqual(result.primitives, []);
  assert.deepEqual(result.bootstrap, []);
  const exit = result.entries.findIndex(e => e.ip === 0x8B);
  assert.ok(exit > 0);
  for (const entry of result.entries.slice(0,exit)) {
    assert.ok(scanner.has(entry.ip));
    assert.deepEqual([entry.r2,entry.r5,entry.pc,entry.r26,entry.r38],
      [8,0,0xD7,0,13]);
  }
  assert.equal(result.entries[exit].afterR2, 0);
  if (keys[0] === 'F' || keys[0] === 'Сx') {
    const scan = result.entries.filter(e => e.ip === 0x60).slice(0,3);
    assert.deepEqual(scan.map(e => e.pc), [0xD5,0xD6,0xD7]);
    assert.deepEqual(scan.map(e => e.next), [0x61,0x61,0x08]);
    for (const e of scan)
      assert.deepEqual([e.r2,e.r26,e.r25,e.r32,e.r38], [15,1,7,0,8]);
    const at7c = result.checkpoints.find(c => c.fields.ip === 0x7C);
    const at77 = result.checkpoints.find(c => c.fields.ip === 0x77);
    assert.ok(at7c && at77);
    assert.equal(at77.fields.r38, 8);
    if (keys[0] === 'Сx') assert.equal(at77.snapshot.r[27], 3);
    const aligned = result.checkpoints.find(c => c.fields.ip === 0x60);
    assert.deepEqual([aligned.fields.pc,aligned.fields.r2,aligned.fields.r26,
      aligned.fields.r25,aligned.fields.r31,aligned.fields.r32,aligned.fields.r38],
      [0xD7,15,1,7,7,0,8]);
    if (keys.length === 2)
      assert.deepEqual([result.final.r[2],result.final.r[5]], [0,15]);
  }
  if (keys[0] === 'K' && keys[1] === 'БП') {
    const reads = result.entries.filter(e => e.ip === 0xDD);
    assert.ok(reads.length > 0);
    assert.ok(reads.every(e => e.r2 === 0));
  }
  console.log('PASS:', keys.join(' '), 'from keyboard-prepared D7; no C7/C8');
}
console.log('PASS: six native cases. F ВП reaches aligned ROM 60 at D7, '+
  'R2=F/R26=1/R32=0, but selector 8 chooses 08 rather than 18 or C8.');
