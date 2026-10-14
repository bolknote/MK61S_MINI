#!/usr/bin/env node
'use strict';
// Validate conservative ROM masks against PASSIVE actual outputs, including
// both downstream chips via carrier identities. Not a new bank constructor.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {masks}=require('./cache-bc-head93-rom-memory-masks.cjs');
const numeric=a=>a.filter(j=>j<=34&&j%3===1);
assert.deepEqual(numeric(masks('ik1302',0xA3).write),[28,31,34]);
assert.deepEqual(numeric(masks('ik1302',0xE7).write),Array.from({length:12},(_,j)=>1+3*j));
assert.deepEqual(numeric(masks('ik1302',0xD4).write),[]);
let words=0,changed=0;
for(const file of process.argv.slice(2)) {
  const data=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(data.schema,'mk61-two-word-reopen-passive-v1');
  for(const records of Object.values(data.windows))for(const v of records) {
    const after=new Map();
    for(const [name,tags] of Object.entries(v.tagsAfter))
      tags.forEach((tag,j)=>after.set(tag,v.fullAfter[name].m[j]));
    for(const chip of ['ik1302','ik1303','ik1306']) {
      const state=v.fullBefore[chip],ip=state.r[36]+16*state.r[39];
      const possible=new Set(masks(chip,ip).write);
      for(let j=0;j<42;j++)if(after.get(v.tagsBefore[chip][j])!==state.m[j]) {
        assert.ok(possible.has(j),file+'/'+v.word+'/'+chip+'/'+ip.toString(16)+' unexpected changed cell'+j);
        changed++;
      }
    }
    words++;
  }
}
console.log('PASS original ROM masks A3/E7/D4 plus',words,
  'native ALL5 records/all3 chips;',changed,'actually changed cells inside conservative masks. '
  +'Read masks/payload-independent controller reachability not proved by this output check.');
