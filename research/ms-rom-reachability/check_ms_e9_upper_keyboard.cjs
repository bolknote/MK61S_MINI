#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const proxy=require('./check_ms_lower_exchange_keyboard.cjs');
const p=require('./probe_ms_upper_marker_w.cjs');
const {options}=require('./check_ms_e9_upper_entry.cjs');
const record=(display,o={})=>proxy.record(display,options(o),p.finish);
const first=record('0,');
for(const o of [{},{phaseOffset:1},{phaseOffset:2},{settleFrames:12,markerFrames:8}]) {
  const a=record('0,',o),b=record('ignored',o);assert.deepEqual(a.actions,b.actions);
  assert.deepEqual(a.actions.filter(x=>x[0]==='key'),first.actions.filter(x=>x[0]==='key'));
  const keys=a.actions.filter(x=>x[0]==='key').length;
  const waits=a.actions.filter(x=>x[0]==='wait').reduce((s,x)=>s+x[1],0);
  console.log('PASS fixed upper E9 entry keys:',JSON.stringify({o,keys,extraFrames:waits,totalFrames:keys*2+waits}));
}
assert.deepEqual(record('0,',{mirrorSource:false,shiftSource:'123',fullUpper:['0','0','0','0']}).actions,first.actions);
console.log('LIMIT: API check excludes the separate fixture; no live getters/setters/import/reset/alignment. This does not prove a safe writer, numeric universality, or physical timing.');
