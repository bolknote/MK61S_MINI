#!/usr/bin/env node
'use strict';
// Targeted stack-lift controls, not an opcode sweep. A singleton F/P7
// writer could permit a later buffer writer without touching P8/P10.
// All snapshots are detached PRIMARY inputs only, never loaded into stock.
const fs=require('node:fs');
const {pagesAt}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=p=>p.filter((_,j)=>j%3===1).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const e=d.endpoints['packet-reopen-control-front3'];
const inlet={state:e.fullBefore.ik1302,pages:pagesAt(d,e),here:names.indexOf(e.numericOwner[0].split(':')[1])};
const holds=p=>raw(p[8])==='007024681357'&&raw(p[10])==='007012345678';
const compact=v=>({held:v.held,ended:v.ended,R41:v.state.r[41],reads:v.reads,
  numericReads:v.numericReads,writers:v.writers,markers:names.filter((_,j)=>v.pages[j][22]===15),
  P7:raw(v.pages[7]),P8:raw(v.pages[8]),P10:raw(v.pages[10])});
const cases=['digit','enter','cx'].map(kind=>{
  const first=keyCall(inlet,0,0,{kind,preserved:holds});
  const recall=first.held?keyCall(first,8,0,{preserved:holds}):null;
  return {prelude:kind,first:compact(first),recallF:recall&&compact(recall)};
});
console.log(JSON.stringify({cases,
  boundary:'three stack-entry control hypotheses only; PRIMARY, not native construction/repeat/K1/K2'}));
