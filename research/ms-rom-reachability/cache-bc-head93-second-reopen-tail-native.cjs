#!/usr/bin/env node
'use strict';
// Passive source/control audit of the original late PRIMARY formatter.
// This is still the measured FAILED fresh SWAP, never a repaired device.
const {run}=require('./cache-bc-head93-second-reopen-swap-native.cjs');
const raw=a=>a.slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const data=run({proof:true});
const records=data.windows['packet-reopen-control-swap'];
const selected=records.filter(v=>v.word>=2889680);
console.log(JSON.stringify({rows:selected.map(v=>{
  const a=v.fullBefore.ik1302,b=v.fullAfter.ik1302;
  return {word:v.word,ip:v.ip.toString(16).toUpperCase(),owner:v.numericOwner,
    M:raw(a.m.filter((_,j)=>j%3===1)),A:raw(a.r.filter((_,j)=>j%3===0)),
    B:raw(a.r.filter((_,j)=>j%3===1)),afterA:raw(b.r.filter((_,j)=>j%3===0)),
    out:raw(v.emitted.filter((_,j)=>j%3===1)),R26:a.r[26],R2:a.r[2],
    selector:[a.r[29],a.r[32],a.r[35]],
    returns:[0,1,2].map(j=>a.st[36+j]+16*a.st[39+j]),
    afterIp:b.r[36]+16*b.r[39]};
  }),boundary:'fresh unchanged ALL5 negative SWAP trace; no native recovery claim'}));
