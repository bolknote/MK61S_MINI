#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_quiet_normal_exit.cjs');
const {record}=require('./check_ms_quiet_keyboard.cjs');
for(const responses of [['-1,2345678-42'],[',','-1,2345678-42'],[',',',','-1,2345678-42']]) {
  const a=record(responses,{},p.finish);
  assert.deepEqual(a.reads,responses);
  assert.deepEqual(a,record(responses,{fullUpper:['not read'],sourceValue:'not read',independentP8:'not read'},p.finish));
  const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  console.log('PASS normal upper exit: only keys, waits and declared public guard',JSON.stringify({keys,frames}));
}
assert.throws(()=>record(['0,'],{},p.finish),/Unexpected visible display/);
assert.throws(()=>record([',',',',','],{},p.finish),/No guard display/);
if(process.env.MS_NORMAL_EXIT_UNOBSERVED) {
  const {check}=require('./check_ms_quiet_normal_exit.cjs'),{createHash}=require('node:crypto');
  const o={phaseOffset:2},r=p.run(o);check(r);
  const expected=JSON.parse(JSON.stringify(r.calc)),result=structuredClone(r.result);
  r.traced.events.length=r.traced.writes.length=0;
  const plain=p.run({...o,observe:false});
  assert.deepEqual(plain.result,result);assert.deepEqual(JSON.parse(JSON.stringify(plain.calc)),expected);
  console.log('PASS complete observed/unobserved state:',createHash('sha256').update(JSON.stringify(plain.calc)).digest('hex'));
}
