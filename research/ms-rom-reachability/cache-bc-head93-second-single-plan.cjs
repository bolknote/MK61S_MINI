#!/usr/bin/env node
'use strict';
// Source-selected replacement for the destructive P7..P10 four-word push:
// try the actual ROM STORE epilogue, which can emit a single E7/P7.
// This is a conditional primary calculation, not a native recipe or scan.
const assert=require('node:assert/strict');
const {run}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const model=require('./cache-bc-head93-primary-word-model.cjs');
const {pagesAt,call,auditConnected}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const numeric=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const ordinary=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000';
const data=run({proof:true,phase:'yku',secondPhase:'p9-source-write'});
auditConnected(data,['packet-second-open4','packet-second-open5']);
const rec=data.windows['packet-second-open5'][0],pages=pagesAt(data,rec),template=rec.fullBefore.ik1302;
assert.equal(numeric(pages[10]),FIRST);assert.equal(numeric(pages[3]),SECOND);
const entry=names.indexOf(rec.numericOwner[0].split(':')[1]);
const results=[];
for(const reg of [0,1,2,4,5,9,10,11,13,14]) {
  assert.equal(ordinary(pages[(reg+3)%15]),ZERO);
  const result=call(pages,template,reg,4,entry,undefined,{allowedSources:[ZERO,FIRST,SECOND],
    preserved:p=>numeric(p[10])===FIRST});
  if(result&&numeric(result.pages[7])===SECOND)results.push({reg,operand:result.operand,entry,
    writers:result.writers,markers:names.filter((_,j)=>result.pages[j][22]===15)});
}
const others=[];
const swap=data.windows['payload-exit-run'].find(v=>v.ip===0x9C&&
  v.fullBefore.ik1302.r[30]+16*v.fullBefore.ik1302.r[33]===0x14);
for(const [name,v] of [['enter',data.windows['packet-clean-enter'][0]],
  ['lastx',data.windows['packet-clean-lastx'][0]],['swap',swap]]) {
  if(!v)continue;
  const next=pages.map(p=>p.slice());let a=model.clone(v.fullBefore.ik1302),here=entry;
  a.m=next[here].slice();let held=true,ended=false;const writers=[];
  for(let j=0;j<500;j++) {
    const ip=model.ip(a);if(ip===0xBE){ended=true;break;}
    if([0xE7,0xE8,0xE9,0xA8].includes(ip))writers.push([ip,names[here]]);
    const x=model.step(a,v.keysX[0],v.keysY[0],next[(here+1)%15]);next[here]=x.out;
    a=x.state;here=(here+1)%15;
    if(numeric(next[10])!==FIRST){held=false;break;}
  }
  others.push({name,ended,P10held:held,P7:numeric(next[7]),P7second:held&&numeric(next[7])===SECOND,writers});
}
console.log(JSON.stringify({singleP7Candidates:results,otherSourcePrimitives:others,
  boundary:'conditional word-transfer calculations only; native prefix/data/ALL5 verification still required'}));
