#!/usr/bin/env node
'use strict';
// The q bounds of the two final formatters do not prove keyboard entry.
const assert=require('node:assert/strict');
const p=require('./probe_ms_quiet_normal_exit.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {swap}=require('./check_ms_quiet_upper.cjs');
function check(r) {
  const es=r.traced.events,xs=es.filter(e=>e.stage==='clone-quiet-after-34');
  const accepted=xs.find(e=>e.ip===0x9C&&e.slot==='Y'&&e.nextIp===0x9E);assert.ok(accepted);
  assert.equal(raw(accepted.m),r.before.P8.slice(2));
  const source=xs.find(e=>e.ip===0xD6);assert.ok(source);
  assert.equal(source.slot,'T');assert.equal(raw(source.m,0),'0000F0000000');
  const write=xs.find(e=>e.ip===0xE7&&e.command>source.command);assert.ok(write);
  swap(r,write.command,['P8','P9','P10','marker']);
  const cleared=es.find(e=>e.stage==='clone-quiet-after-35'&&e.ip===0xE7);assert.ok(cleared);
  assert.equal(cleared.slot,'marker');assert.equal(raw(cleared.r,0),'000000000000');
  swap(r,cleared.command,['marker']);
  assert.notDeepEqual(r.after,r.before);
  return {falseControl:accepted.command,wrongSource:source.command,upperPush:write.command,
    erasedRealMarker:cleared.command,notAWorkingExit:true};
}
if(require.main===module) {
  const r=p.run({phaseOffset:1,zeroBeforeMarker:false,verifyExit:true,fullUpper:['-1E-99','-1.23E-42','3333','-1.234E-42']});
  console.log('PASS negative keyboard-entry boundary:',JSON.stringify(check(r)));
}
module.exports={check};
