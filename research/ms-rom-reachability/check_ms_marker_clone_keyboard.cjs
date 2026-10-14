#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {record}=require('./check_ms_lower_exchange_keyboard.cjs');
const {finish}=require('./probe_ms_marker_clone_w.cjs');
for(const o of [{},{phaseOffset:1,sourceCopies:2,swaps:1},
  {phaseOffset:2,sourceCopies:2,swaps:1},
  {phaseOffset:1,refreshSource:true},{settleFrames:12,markerFrames:8},
  {sourceKey:'В↑',sourceMirror:'6',sourceCopies:2,swaps:2}]) {
  const a=record('0,',o,finish),b=record('unreadable',o,finish);
  assert.deepEqual(a.actions,b.actions);
  assert.deepEqual(a.actions,record('0,',{...o,values:['other'],fullUpper:['other']},finish).actions);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  const waits=a.actions.filter(x=>x[0]==='wait').reduce((s,x)=>s+x[1],0);
  console.log('PASS fixed clone keys:',JSON.stringify({o,keys,extraFrames:waits,totalFrames:keys*2+waits}));
}
console.log('LIMIT: API/sequence only, not phase-independent success or hardware timing; separate native fixture excluded.');
