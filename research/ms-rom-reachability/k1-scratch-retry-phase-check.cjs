#!/usr/bin/env node
'use strict';
// Pure public-surface timing arithmetic, not a numeric or native proof.
const assert=require('node:assert/strict');
const {record}=require('./k1-x1-retry-reader-check.cjs');
const p=require('./k1-two-hole-prefix.cjs');
const same=(a,b)=>assert.deepEqual(a,b);
for(const ds of [['7,'],['0,','7,'],['0,','0,','7,'],['0,','0,','0,']]) {
  const a=record(ds,{},p.readScratchAligned),b=record(ds,{incoming:'unread',values:['unread']},p.readScratchAligned);
  same(a,b);same(a.seen,ds);same(a.result.attempts,ds.length);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  const waits=a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),frames=keys*2+waits;
  same(keys,11+15*(ds.length-1));
  same(frames,94+118*(ds.length-1)+(1-ds.length%3+3)%3);same(frames%3,1);
  console.log('PASS aligned scratch retry:',JSON.stringify({displays:ds,keys,frames,residue:frames%3}));
}
