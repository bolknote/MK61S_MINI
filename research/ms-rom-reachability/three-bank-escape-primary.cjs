#!/usr/bin/env node
'use strict';
// Source-directed transfer calendar on detached arrays. No stock instance.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const {FIRST,SECOND,THIRD,names,raw}=require('./cache-bc-head93-third-restore-plan.cjs');
const marks=p=>names.filter((_,j)=>p[j][22]===15);
const compact=v=>({held:v.held,ended:v.ended,decode:v.firstDecode&&{word:v.firstDecode.word,owner:v.firstDecode.owner,
  header:[v.firstDecode.pages[names.indexOf(v.firstDecode.owner)][31],v.firstDecode.pages[names.indexOf(v.firstDecode.owner)][34]]},
  reads:v.reads,numericReads:v.numericReads,writers:v.writers,markers:marks(v.pages),
  bank:Object.fromEntries(['P7','P9','P10'].map(n=>[n,raw(v.pages[names.indexOf(n)])]))});
function run(file,start='packet-third-restore-FIRST') {
  const d=JSON.parse(fs.readFileSync(file,'utf8')),entry=d.endpoints[start];
  assert.equal(d.schema,'mk61-third-restore-passive-v1');
  const inlet={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const template=d.windows['packet-third-restore-FIRST'].find(v=>v.ip===0x9C).fullBefore.ik1302;
  const bank=start==='packet-third-restore-FIRST'?
    p=>raw(p[7])===SECOND&&raw(p[9])===FIRST&&raw(p[10])===THIRD:
    p=>raw(p[7])===SECOND&&raw(p[10])===THIRD;
  const holders=p=>raw(p[7],0)===THIRD&&raw(p[9],0)===SECOND&&raw(p[10],0)===FIRST&&raw(p[11],0)===THIRD;
  assert.ok(bank(inlet.pages)&&holders(inlet.pages));
  const preserve=p=>bank(p)&&holders(p);
  const inventory=Array.from({length:15},(_,reg)=>({reg,raw:raw(inlet.pages[(reg+3)%15],0)}));
  const entries=names.map((name,j)=>({name,j,header:[inlet.pages[j][31],inlet.pages[j][34]]}))
    .filter(({j})=>inlet.pages[j][31]===15?inlet.pages[j][34]>=1:inlet.pages[j][34]>=7);
  // One source of each actual payload class; identical numeric sources have
  // identical push data, though real physical source/operand remains explicit.
  const sourceClasses=[...new Set(inventory.map(v=>v.raw))].filter(v=>['000000000000','0000F0000000',FIRST,SECOND,THIRD].includes(v));
  const requested=sourceClasses.map(value=>inventory.find(v=>v.raw===value));
  const attempts=[],successful=[];
  for(const kind of ['lastx','cx','enter','swap'])for(const lead of [0,6,12,18,24]) {
    const next=keyCall(inlet,0,lead,{kind,preserved:preserve}),c={kind,lead,...compact(next)};
    attempts.push(c);if(next.held&&next.ended)successful.push({kind,lead,next});
  }
  for(const source of requested) {
    const ops=[...new Set(entries.map(({j})=>sourceRoot(inlet.pages,template,6,j)).filter(x=>x!==null)
      .map(root=>(source.reg+11-root+30)%15))];
    for(const operand of ops)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(inlet,operand,lead,{preserved:preserve});
      const match=next.reads[0]?.reg===source.reg&&next.reads[0]?.raw===source.raw;
      attempts.push({kind:'rcl',source,operand,lead,sourceMatched:match,...compact(next)});
      if(next.held&&next.ended&&match)successful.push({kind:'rcl',operand,lead,source,next});
    }
  }
  return{entry:{word:entry.word,markers:marks(inlet.pages),numeric:Object.fromEntries(names.map((n,j)=>[n,raw(inlet.pages[j])])),inventory,entries},
    attempts,successful:successful.map(({next,...action})=>({...action,...compact(next)})),
    boundary:'Source classes plus documented marker pop/push functions in the five compatible calendar residues. PRIMARY only; no general key search/global impossibility.'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],process.argv[3])));
module.exports={run};
