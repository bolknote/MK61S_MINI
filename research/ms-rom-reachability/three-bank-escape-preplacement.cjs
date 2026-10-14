#!/usr/bin/env node
'use strict';
// Directed pre-placement marker route: keep the P9/95 inlet while FIRST
// remains explicitly only in genuine R7. Never create an emulator instance.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const {FIRST,SECOND,THIRD,names,raw}=require('./cache-bc-head93-third-restore-plan.cjs');
const mark=p=>names.filter((_,j)=>p[j][22]===15);
const compact=v=>({held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,writers:v.writers,markers:mark(v.pages),
  bank:Object.fromEntries(names.map((n,j)=>[n,raw(v.pages[j])]))});
function run(file,branch='lastx') {
  const d=JSON.parse(fs.readFileSync(file,'utf8')),entry=d.endpoints['packet-third-restore-dropAux1'];
  const template=d.windows['packet-third-restore-FIRST'].find(v=>v.ip===0x9C).fullBefore.ik1302;
  const preserve=p=>raw(p[7])===SECOND&&raw(p[10])===THIRD&&raw(p[7],0)===THIRD&&
    raw(p[9],0)===SECOND&&raw(p[10],0)===FIRST&&raw(p[11],0)===THIRD;
  let current={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const prefix=branch==='lastx'?{kind:'lastx',operand:0,lead:0}:{kind:'rcl',operand:8,lead:18};
  current=keyCall(current,prefix.operand,prefix.lead,{kind:prefix.kind,preserved:preserve});
  assert.ok(current.held&&current.ended);
  const path=[{action:prefix,...compact(current)}];
  for(let depth=0;depth<3;depth++) {
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const actions=[];
    for(const [reg,source] of [[0,'000000000000'],[3,'0000F0000000'],[7,FIRST],[4,THIRD]]) {
      assert.equal(raw(current.pages[(reg+3)%15],0),source);
      const ops=[...new Set(entries.map(j=>sourceRoot(current.pages,template,6,j)).filter(x=>x!==null).map(root=>(reg+11-root+30)%15))];
      for(const operand of ops)for(const lead of [0,6,12,18,24]) {
        const next=keyCall(current,operand,lead,{preserved:preserve});
        if(next.held&&next.ended&&next.reads[0]?.reg===reg&&next.reads[0]?.raw===source)
          actions.push({action:{kind:'rcl',reg,source,operand,lead},...compact(next),next});
      }
    }
    for(const kind of ['cx','lastx','swap','enter'])for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,0,lead,{kind,preserved:preserve});
      if(next.held&&next.ended)actions.push({action:{kind,operand:0,lead},...compact(next),next});
    }
    // Choose only a strict marker reduction. No queue or arbitrary action
    // exploration; otherwise report the structural alternatives and stop.
    const chosen=actions.find(v=>v.markers.length<mark(current.pages).length);
    path.push({depth,alternatives:actions.map(({next,...v})=>v),chosen:chosen?.action||null});
    if(!chosen)break;
    current=chosen.next;
  }
  return{path,boundary:'Detached PRIMARY pre-final-placement marker reduction. FIRST stays an ordinary reserve; not independent three-bank memory or a native path.'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],process.argv[3])));
module.exports={run};
