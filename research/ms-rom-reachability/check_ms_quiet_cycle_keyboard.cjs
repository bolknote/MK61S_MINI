#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {record}=require('./check_ms_quiet_keyboard.cjs');
const four=require('./probe_ms_quiet_read_four.cjs');
const restore=require('./probe_ms_quiet_upper_restore.cjs');
const guard='-1,2345678-42';
for(const responses of [[guard],[',',guard],[',',',',guard]])for(const [name,p,keyBase,frameBase] of [
  ['four copies',four,84,506],['upper restoration',restore,104,634]]) {
  const r=record(responses,{},p.finish);assert.deepEqual(r.reads,responses);
  assert.deepEqual(r.actions,record(responses,{sourceValue:'not read',fullUpper:['not read'],independentP8:'not read'},p.finish).actions);
  const keys=r.actions.filter(x=>x[0]==='key').length;
  const frames=2*keys+r.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  assert.equal(keys,keyBase+responses.length);assert.equal(frames,frameBase+10*responses.length);
  console.log('PASS only keys and the initial public stop:',JSON.stringify({operation:name,keys,frames}));
}
for(const p of [four,restore]) {
  assert.throws(()=>record(['0,'],{},p.finish),/Unexpected visible display/);
  assert.throws(()=>record([',',',',','],{},p.finish),/No guard display/);
}
console.log('LIMIT: no hidden state access; fixture and numeric/timing preconditions are separate from this surface contract.');
