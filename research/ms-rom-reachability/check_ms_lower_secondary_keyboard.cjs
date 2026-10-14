#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const proxy=require('./check_ms_lower_exchange_keyboard.cjs');
const {finish}=require('./probe_ms_lower_secondary_exchange.cjs');
const record=(display,o={})=>proxy.record(display,o,finish);
function main() {
  const baseline=record('0,');
  for(const o of [{},{phaseOffset:1},{phaseOffset:2},{settleFrames:12,markerFrames:8}]) {
    const a=record('0,',o),b=record('not a number',o);
    assert.deepEqual(a.actions,b.actions);
    assert.deepEqual(a.actions.filter(x=>x[0]==='key'),baseline.actions.filter(x=>x[0]==='key'));
    const keys=a.actions.filter(x=>x[0]==='key').length;
    assert.equal(keys,339);
    const wait=a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
    console.log('PASS fixed secondary-W exchange keyboard:',JSON.stringify({options:o,keys,extraWaitFrames:wait,totalFrames:keys*2+wait}));
  }
  assert.deepEqual(record('anything',{bank:['-1E-99'],values:['123'],fullUpper:['0']}).actions,baseline.actions);
  console.log('PASS: no hidden state access, setters, reset, import, alignment or display-dependent decisions.');
  console.log('LIMIT: the fixed sequence still has a native Q-entry counterexample; keyboard-only is not correctness for arbitrary data/timing.');
}
if(require.main===module)main();
module.exports={record};
