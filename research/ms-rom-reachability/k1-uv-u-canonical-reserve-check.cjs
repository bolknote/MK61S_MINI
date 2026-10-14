#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {verify}=require('./k1-uv-u-canonical-reserve.cjs');
const {checkGuard}=require('./arbitrary-bank-pair-zero-capture-keyboard-check.cjs');
const files=['/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs','/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs',
  ...['ik1302_symbolic.py','analyze_gates.py','audit_ms_rom_control.py','k1-formatter-entry-audit.py'].map(n=>__dirname+'/'+n)];
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const cases=[{},
  {values:['811','822','-9.8765432E23','0'],phaseOffset:2},
  {values:['811','822','-9.8765432E23','-8.7654321E-99'],phaseOffset:0},
  {values:['811','822','-9.8765432E23','-8.7654321E99'],phaseOffset:1}];
function main(){
  checkGuard();const frozen=Object.fromEntries(files.map(f=>[f,hash(f)]));
  for(const o of cases)console.log('PASS canonical U reserve',JSON.stringify(verify(o)));
  for(const [f,h] of Object.entries(frozen))assert.equal(hash(f),h);
  console.log(JSON.stringify({cases:cases.length,frozenSixUnchanged:true,
    boundary:'canonical real LastX U reserve/readback; not a reverse writer, full K1 or universal numeric/timing proof'}));
}
if(require.main===module)main();
module.exports={cases,main};
