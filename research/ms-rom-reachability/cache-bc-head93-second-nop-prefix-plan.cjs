#!/usr/bin/env node
'use strict';
// Test the known K0/54 no-op as a CONTROL prelude, not a numerical source.
// Detached PRIMARY from one actual V/aux0 endpoint, not an emulator import.
const fs=require('node:fs');
const {pagesAt}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=p=>p.filter((_,j)=>j%3===1).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const e=d.endpoints['packet-reopen-control-front3'];
const inlet={state:e.fullBefore.ik1302,pages:pagesAt(d,e),here:names.indexOf(e.numericOwner[0].split(':')[1])};
const holds=p=>raw(p[8])==='007024681357'&&raw(p[10])==='007012345678';
console.log(JSON.stringify({cases:[0,6,12,18,24].map(lead=>{
  const v=keyCall(inlet,0,lead,{kind:'nop',preserved:holds});
  return{lead,decoded:v.firstDecode?.owner,held:v.held,ended:v.ended,reads:v.reads,
    numericReads:v.numericReads,writers:v.writers,
    numeric:Object.fromEntries(names.map((n,j)=>[n,raw(v.pages[j])]))};
}),boundary:'PRIMARY K0 control-prelude hypotheses only; no native new reader/repeat/full K1/K2'}));
