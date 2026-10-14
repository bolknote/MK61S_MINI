#!/usr/bin/env node
'use strict';
// A second, separate real fragment: high R1 and PC58 through D5. It does
// not provide the 600 read or the saved-tail preparation at the same AC.
const assert=require('node:assert/strict');
const {prepare}=require('./check_600_keyboard.cjs');
const {trace}=require('./probe_ee_ring_source.cjs');

function run() {
  const calc=prepare(true,{input:'1E72',multiplier:'1.0000005E4'});
  const result=trace(calc,c=>{c.pressSequence(['В/О','С/П']);c.runFrames(6);});
  const reads=result.events.filter(e=>e.ip===0xEE && e.raw==='580010000005');
  assert.ok(reads.length>=3);
  const ac=result.events.filter(e=>e.ip===0xAC && e.r1===5);
  assert.ok(ac.length>=3);
  assert.ok(ac.every(e=>e.pc===0x58 && e.st32===0 && e.st35===0));
  const route=('AC E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A '+
    '93 94 95 98 9A E4 DE D5 '+Array(11).fill('9B').join(' ')+
    ' 9C 9E 9F AA').split(' ').map(v=>parseInt(v,16));
  for(let i=0;i<ac.length-1;i++) {
    assert.deepEqual(ac[i].route,route);
    assert.equal(ac[i+1].command-ac[i].command,45,'observed three-ring-turn period');
    assert.equal(ac[i+1].r2,ac[i].r2===0?12:0);
  }
  assert.deepEqual(result.primitives,[]);
  console.log('PASS: actual word 580010000005 produces AC with PC58 and R1=5; '+
    `${ac.length} observed entries, 45-command spacing, R2 alternates C/0. `+
    'ST32=ST35=0 and EE header stays 5: this is not the 600/A9/C8 preparation.');
  return result;
}
if(require.main===module)run();
module.exports={run};
