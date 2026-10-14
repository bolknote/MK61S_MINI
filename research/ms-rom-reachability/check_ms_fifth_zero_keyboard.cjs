#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {record}=require('./check_ms_quiet_keyboard.cjs');
const {finish,tail}=require('./probe_ms_quiet_fifth_zero.cjs');
const guard='-1,2345678-42';
for(const responses of [[guard],[',',guard],[',',',',guard]]) {
  const r=record(responses,{},finish);assert.deepEqual(r.reads,responses);
  assert.deepEqual(r.actions,record(responses,{sourceValue:'not read',fullUpper:['not read'],independentP8:'not read'},finish).actions);
  for(const [i,keys] of tail().entries()) {
    const stage='clone-quiet-after-'+(5+i);
    assert.deepEqual(r.actions.filter(x=>x[2]===stage),[...keys.map(k=>['key',k,stage]),['wait',8,stage]]);
  }
  const keys=r.actions.filter(x=>x[0]==='key').length;
  const frames=2*keys+r.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  assert.equal(keys,74+responses.length);assert.equal(frames,446+10*responses.length);
  console.log('PASS protected fifth-word backup uses only keys and initial public stop:',JSON.stringify({keys,frames}));
}
assert.throws(()=>record(['0,'],{},finish),/Unexpected visible display/);
assert.throws(()=>record([',',',',','],{},finish),/No guard display/);
console.log('LIMIT: fixed emulator-frame gaps, canonical b/c classes and working fixture are not a complete K1 contract.');
