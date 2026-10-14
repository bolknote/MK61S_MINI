#!/usr/bin/env node
'use strict';
// Eleven named, source-motivated negative controls, NOT keyboard search.
// Only public keyboard/numeric-entry APIs on isolated fresh references.
// The instance tick wrapper observes; a fresh uninstrumented ALL5 mirror
// verifies that it does not change any chip state. No ROM/reference edits,
// register/program setters, loaded symbolic packet or return/IP repair.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const reference = path.resolve(__dirname, '../../../..', 'Projects/MK-61/tests/emulator');
const nativePath = path.join(reference, 'mk61.cjs');
const romPath = path.join(reference, 'rom.cjs');
const expected = [
  'b15bc586ac3804eb5622b8072e88f35bcd2081abbe2195fcefa5a718e56ece0c',
  '6c3f85b3e942cdd4d4191e46e98a50829eb850011b8b7a3cc01b12e5e2a31a33',
];
function hashes() {
  assert.deepEqual([nativePath, romPath].map(p =>
    crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')), expected);
}
hashes();
const { MK61 } = require(nativePath);
const ready = c => c.inputNumber('12345678', { clear: true });
const register = (c, r, value) => c.inputNumber(value, { clear: true })
  .pressSequence(['X→П', r]);
const program = (c, r, indirect = false) => c.pressSequence([
  'В/О', 'F', 'ВП', ...(indirect ? ['K'] : []), 'П→X', r,
  'С/П', 'F', '/-/', 'В/О',
]);
const cases = [
  { name: 'manual_read_D', prepare: ready,
    run: c => c.pressSequence(['П→X', 'Сx']).runFrames(4) },
  { name: 'program_read_D', prepare: c => { program(c, 'Сx'); ready(c); },
    run: c => c.press('С/П').runFrames(4), opcode: 0x6D },
  ...['2', '3'].map(r => ({ name: `manual_indirect_${r}`,
    prepare: c => { register(c, r, '5'); ready(c); },
    run: c => c.pressSequence(['K', 'П→X', r]).runFrames(4) })),
  ...['2', '3'].map(r => ({ name: `program_indirect_${r}`,
    prepare: c => { program(c, r, true); register(c, r, '5'); ready(c); },
    run: c => c.press('С/П').runFrames(4), opcode: 0xD0 + Number(r) })),
  ...['2', '3'].map(r => ({ name: `program_entry_${r}`, prepare: ready,
    run: c => c.pressSequence(['В/О', 'F', 'ВП', 'K', 'П→X', r]).runFrames(2),
    opcode: 0xD0 + Number(r) })),
  { name: 'read_D_exponent23', prepare: c => {
      register(c, 'Сx', '1E23'); ready(c);
    }, run: c => c.pressSequence(['П→X', 'Сx']).runFrames(4) },
  { name: 'old_X_exponent23', prepare: c => c.inputNumber('1E23', { clear: true }),
    run: c => c.pressSequence(['П→X', 'Сx']).runFrames(4) },
  // Literal MANUAL-key translation of the supplied B3-34 article's
  // example. Not a claim of correct B3-34 reproduction, ghost creation
  // on every hardware revision or successful hidden-number retrieval.
  { name: 'article_manual_translation', prepare: c => {
      register(c, '9', '111111');
      c.pressSequence(['Сx', '0', '0', '0', '/', 'ВП', 'K', '0']);
    }, run: c => c.pressSequence([
      'В↑', 'П→X', '9', 'В↑', 'В↑', 'В↑', 'В↑', 'В↑',
    ]) },
];
assert.equal(cases.length, 11);

function dump(c) {
  const fields = ['memory', 'r', 'stack', 'tickIndex', 's', 's1', 'l', 't',
    'carry', 'input', 'output', 'keyX', 'keyY', 'command', 'syncAddress', 'commas'];
  return ['ik1302', 'ik1303', 'ik1306', 'ir2a', 'ir2b'].map(name =>
    fields.map(field => c[name][field]));
}
function sample(c) {
  const p = c.ik1302;
  return { ip: p.r[36] + 16*p.r[39], type: p.r[32], kind: p.r[35],
    counter: p.r[26], s1: p.s1, vector: p.r[37] + 16*p.r[40],
    b11: p.r[34], stack: [0, 1, 2].map(j => p.stack[36+j] + 16*p.stack[39+j]) };
}
function critical(s) {
  if (!(s.counter === 0 && s.kind === 13 && [2, 3].includes(s.type))) return false;
  if (s.ip === 0xE4) return s.s1 === 4 && s.vector === 0xD8
    && s.stack.join() === [0xAD, 0xDD, 0xE5].join();
  if (s.ip === 0xA3) return s.s1 === 9 && s.vector === 0xCC && s.b11 === 6
    && ([0x93, 0xDD].includes(s.stack[0]))
    && s.stack[1] === 0xE5 && s.stack[2] === 0xAD;
  return false;
}

let totalWords = 0, nearest = 0;
for (const spec of cases) {
  const c = new MK61(), mirror = new MK61();
  spec.prepare(c); spec.prepare(mirror);
  const original = c.tick.bind(c); const selected = [];
  let words = 0, criticalCount = 0, writerCount = 0;
  c.tick = function () {
    if (this.ik1302.tickIndex === 0) {
      words++; const s = sample(this);
      if (critical(s)) criticalCount++;
      if ([0xBB, 0xBC].includes(s.ip)) writerCount++;
      if (s.ip === 0xEE && s.counter === 0 && s.kind === 13 && [2, 3].includes(s.type)) {
        selected.push(s); nearest++;
      }
    }
    return original();
  };
  spec.run(c); spec.run(mirror);
  assert.deepEqual(dump(c), dump(mirror), spec.name + ' passive ALL5 mirror');
  assert.equal(c.displayText(), mirror.displayText());
  if (spec.opcode !== undefined) assert.equal(c.readCommand(0), spec.opcode);
  assert.equal(criticalCount, 0, spec.name + ' unexpectedly reached critical packet');
  assert.equal(writerCount, 0, spec.name + ' unexpectedly reached BB/BC');
  totalWords += words;
  console.log(JSON.stringify({ case: spec.name, words, display: c.displayText(),
    criticalCount, writerCount, earlierEE: selected }));
}
hashes();
console.log(`PASS ${cases.length} NAMED native negative controls, ${totalWords} observed `
  + `primary words, ${cases.length} fresh uninstrumented ALL5 mirrors. `
  + `${nearest} earlier EE packets are NOT the required CC/AD inlet. `
  + 'No native source factory/Ms transfer or global reachability exclusion claim.');
