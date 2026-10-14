#!/usr/bin/env node
'use strict';
// Fourteen source-selected controls: direct/indirect read of arithmetic-created
// header6, from ordinary X and the already documented700 signature.
// Public keys on fresh stock references only, passive observations and fresh
// unobserved ALL5 mirrors. No symbolic packet, setters, state/IP/ROM repair.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const reference = '/Users/bolk/Projects/MK-61/tests/emulator/';
const sources = ['mk61.cjs', 'rom.cjs'];
const expected = [
  'b15bc586ac3804eb5622b8072e88f35bcd2081abbe2195fcefa5a718e56ece0c',
  '6c3f85b3e942cdd4d4191e46e98a50829eb850011b8b7a3cc01b12e5e2a31a33',
];
const hashes = () => assert.deepEqual(sources.map(n =>
  crypto.createHash('sha256').update(fs.readFileSync(reference+n)).digest('hex')), expected);
hashes();
const { MK61 } = require(reference+'mk61.cjs');
const registerKeys = [...'0123456789', ',', '/-/', 'ВП', 'Сx', 'В↑'];
const fields = ['memory', 'r', 'stack', 'tickIndex', 's', 's1', 'l', 't',
  'carry', 'input', 'output', 'keyX', 'keyY', 'command', 'syncAddress', 'commas'];
const dump = c => ['ik1302', 'ik1303', 'ik1306', 'ir2a', 'ir2b'].map(n =>
  fields.map(f => c[n][f]));
function aligned(c) {
  assert.ok([0, 84, 168].includes(c.ir2a.tickIndex));
  c.runFrames((1-c.ir2a.tickIndex/84+3) % 3);
  assert.equal(c.ir2a.tickIndex, 84); return c;
}
function rawRegister(c, index) {
  assert.equal(c.ir2a.tickIndex, 84);
  const [chip, end] = c.commandAddress(index*7, 1), mem = c.memoryForChip(chip);
  return Array.from({length: 12}, (_, i) => mem[end-8-3*i].toString(16).toUpperCase()).join('');
}
function arithmetic(c, input, multiplier, store=null) {
  c.pressSequence(['В/О', 'F', 'ВП', 'F', '*', 'F', '*', 'F', '*',
    'П→X', '0', '*', ...(store === null ? [] : ['X→П', registerKeys[store]]),
    'С/П', 'F', '/-/', 'В/О']);
  const commands = [0x22, 0x22, 0x22, 0x60, 0x12,
    ...(store === null ? [] : [0x40+store]), 0x50];
  assert.deepEqual(commands.map((_, i) => c.readCommand(i)), commands);
  c.inputNumber(multiplier, {clear: true}).pressSequence(['X→П', '0']);
  c.inputNumber(input, {clear: true}); return aligned(c);
}
function setup(signature, pointerSeed, pointerRegister=3, jump210=false, jumpDirectD2=false) {
  const c = new MK61(); assert.equal(c.extended, true); // Stock three-chip MK61.
  for (const name of ['setRegister', 'writeCommand', 'loadProgram', 'writeNumber'])
    c[name] = () => { throw Error('Forbidden state setter: '+name); };
  c.inputNumber('1', {clear: true}).pressSequence(['X→П', '2']);
  c.inputNumber(pointerSeed, {clear: true}).pressSequence(['X→П', registerKeys[pointerRegister]]);
  if (jump210) c.inputNumber('210', {clear: true}).pressSequence(['X→П', '4']);
  arithmetic(c, '1E75', '1.0000003', 9);
  c.pressSequence(['В/О', 'С/П']).runFrames(12); aligned(c);
  assert.equal(rawRegister(c, 9), '600010000003');
  if (signature) {
    arithmetic(c, '1E87', '1.0000005E4');
    c.pressSequence(['В/О', 'С/П']).runFrames(12);
    c.pressSequence(['F', '/-/']);
    c.pressSequence(['F', 'ВП']).runFrames(4);
    c.press('В↑').runFrames(4);
    c.pressSequence(['F', '/-/']).runFrames(4);
    c.pressSequence(['БП', '5', '8']).runFrames(4);
    c.pressSequence(['БП', '5', '8']).runFrames(4); aligned(c);
  } else c.inputNumber('12345678', {clear: true}), aligned(c);
  if (jump210) c.pressSequence(['K', 'БП', '4']).runFrames(4), aligned(c);
  if (jumpDirectD2) c.pressSequence(['БП', 'Сx', '2']).runFrames(4), aligned(c);
  assert.equal(rawRegister(c, 9), '600010000003');
  return c;
}
function sample(c) {
  const p = c.ik1302;
  return { ip: p.r[36]+16*p.r[39], C: [p.r[26], p.r[32], p.r[35]],
    ST1: [p.stack[25], p.stack[31], p.stack[34]],
    ST2: [p.stack[26], p.stack[32], p.stack[35]],
    vector: p.r[37]+16*p.r[40], Bbyte: p.r[31]+16*p.r[34], S1: p.s1, A11: p.r[33],
    tags: [0, 1, 2].map(j => p.stack[36+j]+16*p.stack[39+j]) };
}
function run() {
let mirrors = 0;
const readers = [{indirect: false, pointerSeed: '10'},
  {indirect: true, pointerSeed: '9'}, {indirect: true, pointerSeed: '10'},
  {indirect: true, pointerSeed: '10', pointerRegister: 2},
  {indirect: false, pointerSeed: '10', jump210: true},
  {indirect: false, pointerSeed: '10', jumpDirectD2: true},
  {indirect: false, pointerSeed: '10', jumpDirectD2: true, repeatRead: 2}];
const focused = process.argv.includes('--focus-d2');
for (const signature of [false, true]) for (const spec of readers) {
  const {indirect, pointerSeed, pointerRegister=3, jump210=false, jumpDirectD2=false, repeatRead=1} = spec;
  if (focused && (!signature || !jumpDirectD2)) continue;
  const c = setup(signature, pointerSeed, pointerRegister, jump210, jumpDirectD2);
  const plain = setup(signature, pointerSeed, pointerRegister, jump210, jumpDirectD2);
  const pointerBefore = rawRegister(c, pointerRegister), prepared = sample(c);
  assert.deepEqual(dump(c), dump(plain), 'fresh unobserved preparation');
  const unique = new Map(), original = c.tick.bind(c);
  let words = 0, writer = 0, fullInlet = 0, C8 = 0;
  c.tick = function () {
    if (this.ik1302.tickIndex === 0) {
      words++; const s = sample(this);
      if (s.ip === 0xC8) C8++;
      if ([0xBB, 0xBC].includes(s.ip)) writer++;
      if (s.ip === 0xE3 && s.tags[0] === 0xAD && s.vector === 0xD3 && s.S1 === 13
          && s.ST1[0] === 0 && [2, 3].includes(s.ST1[1]) && s.ST1[2] === 13
          && s.A11 === 6) fullInlet++;
      if ([0xAC, 0xEE, 0xE3, 0xE4, 0xA3, 0xBB, 0xBC].includes(s.ip))
        unique.set(JSON.stringify(s), s);
    }
    return original();
  };
  const keys = indirect ? ['K', 'П→X', registerKeys[pointerRegister]] : ['П→X', '9'];
  const stages = [];
  for (let n=0; n<repeatRead; n++) {
    for (const x of [c, plain]) { x.pressSequence(keys).runFrames(8); aligned(x); }
    assert.deepEqual(dump(c), dump(plain)); stages.push(sample(c));
  }
  assert.deepEqual(dump(c), dump(plain), 'fresh unobserved entire suffix ALL5 mirror');
  assert.equal(c.displayText(), plain.displayText()); mirrors++;
  console.log(JSON.stringify({case: (signature ? 'signature700_' : 'ordinaryX_')
    +(indirect ? 'indirect'+pointerRegister+'_seed'+pointerSeed : 'direct_ghost9')
    +(jump210 ? '_jump210' : '')+(jumpDirectD2 ? '_directAddressD2' : '')
    +(repeatRead>1 ? '_readTwice' : ''), keys, stages,
    pointerSeed, pointerBefore, pointerAfter: rawRegister(c, pointerRegister),
    prepared, words, writer, fullInlet, C8,
    display: c.displayText(), selected: [...unique.values()], ALL5mirror: true}));
}
assert.equal(mirrors, focused ? 2 : 14); hashes();
console.log(`PASS ${mirrors} source-selected header6 controls/fresh ALL5 mirrors. `
  + 'These observations, not loaded symbolic hypotheses, decide whether an '
  + 'entry was reached. No live hardware/physical exchange or global exclusion claim.');
}
if (require.main === module) run();
module.exports = {setup, arithmetic, aligned, rawRegister, dump, sample, hashes};
