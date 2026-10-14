#!/usr/bin/env node
'use strict';
// Passive capacity audit of the ACTUAL closed two-number repeat. Preserve
// references/ROM/state, collect only potential writes at observed IPs.
const assert=require('node:assert/strict');
const {run}=require('./cache-bc-head93-second-p7-repeat-native.cjs');
const v=run({proof:process.argv.includes('--proof-input')});
assert.equal(v.repeatDiagnostic.equal,true);
const f=v.report.bankFootprint;
assert.equal(f.checkedWords,880380);
for(const n of ['U','V','W','Q','P8'])assert.equal(f.pages[n]?.writeMask,0xFFF,n+' working word');
for(const n of ['P7','P9','P10'])assert.equal(f.pages[n]?.writeMask||0,0,n+' no potential writer at observed IPs');
const fields=mask=>Array.from({length:12},(_,j)=>j).filter(j=>mask&(1<<j));
const result={cycle:v.repeatDiagnostic,potential:f.checkedWords,
  pages:Object.fromEntries(['U','V','W','Q','P7','P8','P9','P10'].map(name=>{
    const p=f.pages[name]||{readMask:0,writeMask:0,witness:{}};
    return[name,{read:fields(p.readMask),write:fields(p.writeMask),
      writeWitness:Object.fromEntries(Object.entries(p.witness).filter(([key])=>key.startsWith('write:')))}];
  })),boundary:f.boundary};
console.log(JSON.stringify(process.argv.includes('--proof-input')?{...v,capacity:result}:result));
