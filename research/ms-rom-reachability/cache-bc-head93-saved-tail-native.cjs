#!/usr/bin/env node
'use strict';
// Five named saved-header controls. Fresh stock references/public keys only;
// optional tick wrapper observes. Fresh unobserved ALL5 mirrors are compared.
// No setters, loaded symbolic states, ROM/IP/return edits, hardware or browser.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const reference = '/Users/bolk/Projects/MK-61/tests/emulator';
const paths = ['mk61.cjs', 'rom.cjs'].map(n => path.join(reference, n));
const expected = [
  'b15bc586ac3804eb5622b8072e88f35bcd2081abbe2195fcefa5a718e56ece0c',
  '6c3f85b3e942cdd4d4191e46e98a50829eb850011b8b7a3cc01b12e5e2a31a33',
];
const hashes = () => assert.deepEqual(paths.map(p =>
  crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')), expected);
hashes();
const { MK61 } = require(paths[0]);
const fields = ['memory', 'r', 'stack', 'tickIndex', 's', 's1', 'l', 't',
  'carry', 'input', 'output', 'keyX', 'keyY', 'command', 'syncAddress', 'commas'];
const dump = c => ['ik1302', 'ik1303', 'ik1306', 'ir2a', 'ir2b'].map(n =>
  fields.map(f => c[n][f]));
const sample = c => {
  const p = c.ik1302;
  return { ip: p.r[36]+16*p.r[39], C: [p.r[26], p.r[32], p.r[35]],
    ST1: [p.stack[25], p.stack[31], p.stack[34]],
    ST2: [p.stack[26], p.stack[32], p.stack[35]],
    vector: p.r[37]+16*p.r[40] };
};
const mirror = (c, plain) => {
  assert.deepEqual(dump(c), dump(plain));
  assert.equal(c.displayText(), plain.displayText());
};
let mirrors = 0;
for (const reg of ['2', '3']) {
  const c = new MK61(), plain = new MK61();
  const stages = [
    x => x.inputNumber('5', {clear: true}).pressSequence(['X→П', reg]),
    x => x.inputNumber('12345678', {clear: true}),
    x => x.pressSequence(['K', 'П→X', reg]).runFrames(4),
  ];
  const reports = [];
  for (const [stage, run] of stages.entries()) {
    run(c); run(plain); mirror(c, plain); reports.push({stage, ...sample(c)});
  }
  assert.deepEqual(reports.at(-1).ST2, [0, 0, 0]);
  assert.deepEqual(reports.at(-1).ST1.slice(1), [0, 0]);
  console.log(JSON.stringify({case: 'indirect_'+reg+'_saved_tail', reports,
    display: c.displayText(), ALL5mirror: true}));
  mirrors++;
}
for (const input of ['0', '12345678']) {
  const c = new MK61(), plain = new MK61();
  c.inputNumber(input, {clear: true}); plain.inputNumber(input, {clear: true});
  const selected = []; const original = c.tick.bind(c);
  c.tick = function () {
    if (this.ik1302.tickIndex === 0) {
      const s = sample(this);
      if ([0xAB, 0xAD, 0xA2, 0xA3, 0xAC, 0xE3, 0xE4].includes(s.ip)
          && selected.length < 80) selected.push(s);
    }
    return original();
  };
  c.pressSequence(['K', 'ВП']).runFrames(4);
  plain.pressSequence(['K', 'ВП']).runFrames(4); mirror(c, plain);
  assert.ok(selected.length < 80, 'selected event capture must not be capped');
  assert.ok(selected.some(s => s.ip === 0xA3 && s.C[1] === 9 && s.C[2] === 3));
  assert.ok(!selected.some(s => s.ip === 0xE3 && s.ST1[0] === 0
    && [2, 3].includes(s.ST1[1]) && s.ST1[2] === 13));
  console.log(JSON.stringify({case: 'K_EXP_saved_tail_'+input, selected,
    display: c.displayText(), ALL5mirror: true}));
  mirrors++;
}
const c = new MK61(), plain = new MK61();
for (const x of [c, plain])
  x.pressSequence(['В/О', 'F', 'ВП', 'K', 'ВП']).runFrames(2);
mirror(c, plain);
assert.equal(c.readCommand(0), 0x39, 'K EXP is XOR39, NOT a public opcode2D');
console.log(JSON.stringify({case: 'program_K_EXP_opcode', opcode: c.readCommand(0),
  ALL5mirror: true}));
mirrors++;
assert.equal(mirrors, 5); hashes();
console.log('PASS five named native controls/five fresh unobserved ALL5 mirrors. '
  + 'K EXP is39, not2D; ordinary KIP2/3 did not leave the saved2/D or3/D packet '
  + 'in these stages. No universal exclusion, native factory or exchange claim.');
