#!/usr/bin/env node
'use strict';
// Setup, program entry and execution are keyboard-only. The observer never
// assigns internal calculator state. ROM addresses are not user opcodes.
const assert = require('node:assert/strict');
const path = require('node:path');
const { MK61 } = require(path.join(process.env.MK61_REFERENCE_ROOT ||
  path.resolve(__dirname, '../../..', 'MK-61'), 'tests/emulator/mk61.cjs'));
const writers = new Set([0x1F,0x59,0x5C,0x5F,0x6C,0x7C,0x85,0xB3,0xCD,0xDD,0xDE,0xE6]);
const hex = n => n.toString(16).toUpperCase().padStart(2, '0');
const address = ch => ch.r[36] + 16*ch.r[39];
const fields = ch => ({ip:address(ch),r0:ch.r[0],r2:ch.r[2],r25:ch.r[25],r26:ch.r[26],
  r29:ch.r[29],r31:ch.r[31],r32:ch.r[32],r34:ch.r[34],r35:ch.r[35],r38:ch.r[38],s1:ch.s1});

const cases = [
  {label:'direct store C',keys:['X→П','ВП'],opcode:0x4C,x:'12'},
  {label:'indirect store C',keys:['K','X→П','ВП'],opcode:0xBC,x:'12'},
  {label:'indirect recall C',keys:['K','П→X','ВП'],opcode:0xDC,x:'12'},
  {label:'indirect jump C',keys:['K','БП','ВП'],opcode:0x8C,x:'12'},
  {label:'indirect call C',keys:['K','ПП','ВП'],opcode:0xAC,x:'12'},
  ...[
    ['x!=0','С/П',0x7C,['0','1']],
    ['x>=0','В/О',0x9C,['1-','1']],
    ['x<0','ШГ→',0xCC,['1-','1']],
    ['x=0','ШГ←',0xEC,['0','1']],
  ].flatMap(([name,key,opcode,values]) => values.map(x =>
    ({label:`indirect ${name} C, X=${x}`,keys:['K',key,'ВП'],opcode,x}))),
];

function run(test, manual=false) {
  const calc = new MK61();
  if (!manual) {
    calc.pressSequence(['F','ВП',...test.keys,'С/П','С/П','С/П','F','/-/','В/О']);
    assert.deepEqual([0,1,2,3].map(i => calc.readCommand(i)),[test.opcode,0x50,0x50,0x50]);
  }
  // ВП is the register-C selector: verify it independently by reading C.
  calc.inputNumber('3',{clear:true}).pressSequence(['X→П','ВП']);
  assert.equal(calc.readRegister('C'),'3,');
  calc.inputNumber(test.x,{clear:true}).press('В/О');
  const chip=calc.ik1302, tick=chip.tick, primitives=[], sources=[];
  let current=null, recording=null;
  chip.tick=function() {
    if (this.tickIndex===0) {
      current=fields(this);
      if (current.ip===0xC7 || current.ip===0xC8) primitives.push(current);
      if (recording) recording.route.push(current);
    }
    const result=tick.call(this);
    if (this.tickIndex===0) {
      const after=fields(this);
      if (recording && writers.has(current.ip)) {
        recording.nextWriter={before:current,after};
        recording=null;
      }
      if (current.ip===0x1F && current.r35===12) {
        assert.equal(after.r38,4);
        recording={before:current,after,route:[]};
        sources.push(recording);
      }
    }
    return result;
  };
  try {
    calc.pressSequence(manual ? test.keys : ['С/П']);
    calc.runUntilStable({maxFrames:12,stableFrames:4});
  } finally {chip.tick=tick;}
  assert.ok(sources.length>0,`${test.label}: no 1F with R35=C`);
  assert.equal(primitives.length,0,`${test.label}: unexpected primitive entry`);
  for (const source of sources) {
    assert.ok(source.nextWriter,`${test.label}: selector lifetime still open`);
    assert.ok(source.route.every(e => e.r38===4));
    assert.ok([0xCD,0xDD,0xE6].includes(source.nextWriter.before.ip),
      `${test.label}: next writer ${hex(source.nextWriter.before.ip)}=`+
      `${hex(source.nextWriter.after.r38)}, route ${source.route.map(e=>hex(e.ip)).join(' ')}`);
    // X is deliberately short; it cannot provide a mantissa-derived 4 via DD.
    const expected = new Map([[0xCD,8],[0xDD,1],[0xE6,12]]);
    assert.equal(source.nextWriter.after.r38,expected.get(source.nextWriter.before.ip));
  }
  return {label:test.label,manual,opcode:test.opcode,x:test.x,
    pc:calc.programCounter(),display:calc.displayText(),sources,primitives};
}

module.exports={run,cases};
if (require.main===module) {
  const reports=cases.map(test => run(test));
  reports.push(run(cases[0],true));
  for (const report of reports) {
    if (process.argv.includes('--json')) console.log(JSON.stringify(report));
    else console.log(`${report.label}${report.manual ? ' [manual]' : ''}: `+
      report.sources.map(s => `1F->${hex(s.after.ip)}, next writer `+
        `${hex(s.nextWriter.before.ip)}=${hex(s.nextWriter.after.r38)}`).join('; '));
  }
  console.log(`PASS: ${reports.length} keyboard-only register-C cases; no C7/C8`);
}
