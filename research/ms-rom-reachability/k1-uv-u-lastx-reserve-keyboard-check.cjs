#!/usr/bin/env node
'use strict';
// Four independent-value native fixtures, strict public-key mirrors and exact
// 630-tetra assertions. This is a reserve constructor, not a complete writer.
const assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const {verify}=require('./k1-uv-u-lastx-reserve.cjs');
const {checkGuard}=require('./arbitrary-bank-pair-zero-capture-keyboard-check.cjs');
const files=['/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs','/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs',
  ...['ik1302_symbolic.py','analyze_gates.py','audit_ms_rom_control.py','k1-formatter-entry-audit.py'].map(n=>__dirname+'/'+n)];
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const cases=[{},
  {values:['811','822','-9.8765432E23','0'],phaseOffset:1},
  {values:['811','822','-9.8765432E23','-8.7654321E42'],phaseOffset:0},
  {values:['811','822','-9.8765432E23','-8.7654321E-42'],phaseOffset:2}];
function main(){
  checkGuard();const frozen=Object.fromEntries(files.map(p=>[p,hash(p)]));
  for(const c of cases){const out=verify(c);assert.equal(out.keys,37);assert.equal(out.bodyFrames,330+out.options.phaseOffset);
    console.log('PASS native U LastX reserve',JSON.stringify(out));}
  for(const [f,h] of Object.entries(frozen))assert.equal(hash(f),h);
  console.log(JSON.stringify({cases:cases.length,frozenSixUnchanged:true,
    boundary:'native U reserve/false Y marker only; no reverse writer, clean exchange, full K1 or universal timing/numeric proof'}));
}
if(require.main===module)main();
module.exports={cases,main};
