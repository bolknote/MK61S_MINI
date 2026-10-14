#!/usr/bin/env node
'use strict';

// Keyboard-only setup and execution. The observer never writes chip state.
const assert = require('node:assert/strict');
const path = require('node:path');
const reference = process.env.MK61_REFERENCE_ROOT || path.resolve(__dirname, '../../..', 'MK-61');
const { MK61 } = require(path.join(reference, 'tests/emulator/mk61.cjs'));
const hex = value => value.toString(16).toUpperCase().padStart(2, '0');
const address = chip => chip.r[36] + 16 * chip.r[39];
const fields = chip => ({r0: chip.r[0], r25: chip.r[25], r26: chip.r[26],
  r31: chip.r[31], r32: chip.r[32], r35: chip.r[35], r38: chip.r[38], s1: chip.s1});

function observe(calc, action) {
  const chip = calc.ik1302;
  const original = chip.tick;
  const writes = [], dd = [], relevant = [], history = [];
  let entry = null, cycles = 0;
  chip.tick = function () {
    if (this.tickIndex === 0) {
      entry = {ip: address(this), ...fields(this), cycle: cycles++,
        word: Array.from({length: 12}, (_, i) => this.r[3*i])};
      history.push(entry);
      if ([0x1F,0x1D,0x25,0x26,0x28,0x7E,0x77,0x6D,0x60,0xC7,0xC8].includes(entry.ip))
        relevant.push(entry);
    }
    const result = original.call(this);
    if (this.tickIndex === 0) {
      const after = {ip: address(this), ...fields(this)};
      entry.next = after.ip;
      if (entry.r38 !== after.r38) writes.push({ip: entry.ip, before: entry.r38,
        after: after.r38, cycle: entry.cycle});
      if (entry.ip === 0xDD) dd.push({before: entry, after});
    }
    return result;
  };
  try {action(calc);} finally {chip.tick = original;}
  return {dd, writes, relevant, history};
}

function run(label, value, expected, indirect = false, pointer = '8') {
  const calc = new MK61();
  if (indirect) calc.inputNumber(pointer, {clear: true}).pressSequence(['X→П','7']);
  calc.inputNumber(value, {clear: true});
  const report = observe(calc, c => c.pressSequence(indirect ? ['K','X→П','7'] : ['X→П','7']));
  const stores = report.dd.filter(d => d.after.ip === 0xD4);
  const summary = {label, value, indirect, pointer, display: calc.displayText(),
    dd: report.dd.map(d => ({ip: hex(d.after.ip), before: d.before, after: d.after})),
    writes: report.writes.map(w => ({...w, ip: hex(w.ip)})),
    tail: report.relevant.filter(e => e.cycle > (stores[0]?.before.cycle ?? -1)).slice(0,16)
      .map(e => ({...e, ip: hex(e.ip)}))};
  if (process.argv.includes('--json')) {
    const start = report.history.findIndex(e => e.ip === 0x1F);
    const end = report.history.findIndex(e => e.ip === 0x7E);
    summary.firstAddressRoute = end < 0 ? [] : report.history.slice(start, end+1)
      .map(e => ({ip: hex(e.ip), r32: e.r32, r35: e.r35}));
    console.log(JSON.stringify(summary));
  } else console.log(`${label}: DD continuations ${report.dd.map(d =>
    `${hex(d.after.ip)}(R0=${d.before.r0}, R38=${d.after.r38})`).join(', ')}; ` +
    `7E continuations ${report.relevant.filter(e => e.ip === 0x7E).map(e => hex(e.next)).join(', ') || 'none'}`);
  assert.ok(stores.length > 0, `${label}: DD->D4 was not executed`);
  assert.ok(stores.some(d => d.before.r0 === expected && d.after.r38 === ((expected+1)&15)),
    `${label}: expected numeric low mantissa nibble was not observed`);
  assert.equal(report.relevant.filter(e => e.ip === 0xC7 || e.ip === 0xC8).length, 0);
  if (indirect && pointer === '3') {
    assert.ok(report.relevant.some(e => e.ip === 0x7E && e.r38 === 4 &&
      e.r26 === 15 && e.r25 === e.r31 && e.r35 === 1 && e.next === 0x71));
  }
}

run('short integer', '3', 0);
run('eighth mantissa digit', '12345673', 3);
run('decimal point shift', '1.2345673', 3);
run('negative number', '12345673-', 3);
run('different eighth digit', '12345678', 8);
run('indirect store', '12345673', 3, true);
run('indirect store with pointer 3', '12345673', 3, true, '3');
console.log('PASS: 7 keyboard-only cases; pointer 3 prepares the gate data but selects 71, not 77');
