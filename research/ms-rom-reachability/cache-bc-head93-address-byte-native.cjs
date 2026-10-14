#!/usr/bin/env node
'use strict';
// SOURCE-derived opcode2D experiment: enter it as a GOTO address byte,
// then execute that operand cell as a command. Public keys, fresh stock
// reference, passive observer, fresh unobserved ALL5 mirrors. No setters,
// loaded symbolic state, ROM/IP/return repair or live hardware/browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const reference = '/Users/bolk/Projects/MK-61/tests/emulator/';
const files = ['mk61.cjs', 'rom.cjs'];
const expected = ['b15bc586ac3804eb5622b8072e88f35bcd2081abbe2195fcefa5a718e56ece0c',
  '6c3f85b3e942cdd4d4191e46e98a50829eb850011b8b7a3cc01b12e5e2a31a33'];
const hashes = () => assert.deepEqual(files.map(n =>
  crypto.createHash('sha256').update(fs.readFileSync(reference+n)).digest('hex')), expected);
hashes();
const { MK61 } = require(reference+'mk61.cjs');
const fields = ['memory', 'r', 'stack', 'tickIndex', 's', 's1', 'l', 't',
  'carry', 'input', 'output', 'keyX', 'keyY', 'command', 'syncAddress', 'commas'];
const dump = c => ['ik1302', 'ik1303', 'ik1306', 'ir2a', 'ir2b'].map(n =>
  fields.map(f => c[n][f]));
const entryKeys = ['В/О', 'F', 'ВП', 'БП', '2', 'Сx', 'С/П', 'F', '/-/'];
function sample(c) {
  const p = c.ik1302;
  return {ip: p.r[36]+16*p.r[39], C: [p.r[26], p.r[32], p.r[35]],
    ST1: [p.stack[25], p.stack[31], p.stack[34]],
    ST2: [p.stack[26], p.stack[32], p.stack[35]],
    vector: p.r[37]+16*p.r[40], S1: p.s1, A11: p.r[33],
    tags: [0, 1, 2].map(j => p.stack[36+j]+16*p.stack[39+j])};
}
function setup(ghost) {
  const c = new MK61(); assert.equal(c.extended, true);
  for (const name of ['setRegister', 'writeCommand', 'loadProgram', 'writeNumber'])
    c[name] = () => {throw Error('Forbidden state setter: '+name);};
  if (ghost) {
    c.pressSequence(['В/О', 'F', 'ВП', 'F', '*', 'F', '*', 'F', '*',
      'П→X', '0', '*', 'X→П', '9', 'С/П', 'F', '/-/', 'В/О']);
    c.inputNumber('1.0000003', {clear: true}).pressSequence(['X→П', '0']);
    c.inputNumber('1E75', {clear: true});
    c.pressSequence(['В/О', 'С/П']).runFrames(12);
  }
  c.pressSequence(entryKeys).runFrames(3);
  assert.deepEqual([0, 1, 2].map(i => c.readCommand(i)), [0x51, 0x2D, 0x50]);
  return c;
}
for (const ghost of [false, true]) {
  const c = setup(ghost), plain = setup(ghost); assert.deepEqual(dump(c), dump(plain));
  const prepared = sample(c), unique = new Map(), original = c.tick.bind(c);
  let writer = 0, fullInlet = 0, constructor = 0, words = 0;
  c.tick = function () {
    if (this.ik1302.tickIndex === 0) {
      words++; const s = sample(this);
      if ([0xBB, 0xBC].includes(s.ip)) writer++;
      if (s.ip === 0xA3 && s.C[1] === 2 && s.C[2] === 13 && s.vector === 0x93) constructor++;
      if (s.ip === 0xE3 && s.tags[0] === 0xAD && s.vector === 0xD3 && s.S1 === 13
          && s.ST1[0] === 0 && [2, 3].includes(s.ST1[1]) && s.ST1[2] === 13
          && s.A11 === 6) fullInlet++;
      if ([0xAB, 0xAD, 0xA2, 0xA3, 0xAC, 0xE3, 0xE4, 0xBB, 0xBC, 0xBE].includes(s.ip))
        unique.set(JSON.stringify(s), s);
    }
    return original();
  };
  const executeKeys = ['БП', '0', '1', 'С/П'];
  for (const x of [c, plain]) x.pressSequence(executeKeys).runFrames(12);
  assert.deepEqual(dump(c), dump(plain)); assert.equal(c.displayText(), plain.displayText());
  console.log(JSON.stringify({case: ghost ? 'opcode2D_ghostX' : 'opcode2D_zeroX',
    entryKeys, executeKeys, prepared, words, writer, fullInlet, constructor,
    display: c.displayText(), selected: [...unique.values()], ALL5mirror: true}));
}
hashes();
console.log('PASS two PUBLIC address-byte opcode2D experiments/two fresh ALL5 mirrors. '
  + 'Operand entry is real, not K EXP39 or a writeCommand setter. '
  + 'Observed constructor/entry counts, not symbolic hypotheses, determine reachability. '
  + 'No physical exchange or native fullK2 claim.');
