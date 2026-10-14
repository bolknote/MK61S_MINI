#!/usr/bin/env node
'use strict';
// Explicit ordinary-holder repair route. Never an independent-Ms claim:
// FIRST=R7, SECOND=R6, THIRD=R4/R8 are required after every calculated word.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const {FIRST,SECOND,THIRD,names,raw}=require('./cache-bc-head93-third-restore-plan.cjs');
const marks=p=>names.filter((_,j)=>p[j][22]===15);
const held=p=>raw(p[7],0)===THIRD&&raw(p[9],0)===SECOND&&raw(p[10],0)===FIRST&&raw(p[11],0)===THIRD;
function compact(v) {
  return{held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,writers:v.writers,markers:marks(v.pages),
    words:Object.fromEntries(names.map((n,j)=>[n,raw(v.pages[j])])),
    ordinary:Object.fromEntries([4,6,7,8].map(n=>['R'+n,raw(v.pages[(n+3)%15],0)]))};
}
function run(file,prelude=[{kind:'cx',operand:0,lead:0}]) {
  const d=JSON.parse(fs.readFileSync(file,'utf8')),entry=d.endpoints['packet-third-restore-FIRST'];
  const template=d.windows['packet-third-restore-FIRST'].find(v=>v.ip===0x9C).fullBefore.ik1302;
  let current={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const prefixSteps=[];
  for(const action of prelude) {
    if(action.kind==='F-route'||action.kind==='source-route') {
      const reg=action.kind==='F-route'?3:action.reg;
      const source=raw(current.pages[(reg+3)%15],0);
      for(let k=0;k<action.count;k++) {
        const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
        const ops=[...new Set(entries.map(j=>sourceRoot(current.pages,template,6,j)).filter(x=>x!==null).map(root=>(reg+11-root+30)%15))];
        let chosen=null;
        for(const operand of ops) {
          const next=keyCall(current,operand,0,{preserved:held});
          if(next.held&&next.ended&&next.reads[0]?.reg===reg&&next.reads[0]?.raw===source) {chosen={operand,next};break;}
        }
        if(!chosen){prefixSteps.push({FRouteFailure:k,ops,...compact(current)});break;}
        current=chosen.next;
        prefixSteps.push({action:{kind:'rcl',reg,source,operand:chosen.operand,lead:0},...compact(current)});
      }
      continue;
    }
    current=keyCall(current,action.operand,action.lead,{kind:action.kind,preserved:held});assert.ok(current.held);
    prefixSteps.push({action,...compact(current)});
  }
  const adapter=prefixSteps.at(-1);
  const candidates=cur=>{
    const entries=names.map((_,j)=>j).filter(j=>cur.pages[j][31]===15?cur.pages[j][34]>=1:cur.pages[j][34]>=7);
    const attempts=[],positive=[];
    for(const [reg,source] of [[3,'0000F0000000'],[0,'000000000000'],[6,SECOND],[7,FIRST],[4,THIRD]]) {
      assert.equal(raw(cur.pages[(reg+3)%15],0),source);
      const ops=[...new Set(entries.map(j=>sourceRoot(cur.pages,template,6,j)).filter(x=>x!==null).map(root=>(reg+11-root+30)%15))];
      for(const operand of ops)for(const lead of [0,6,12,18,24]) {
        const next=keyCall(cur,operand,lead,{preserved:held}),match=next.ended&&next.reads[0]?.reg===reg&&next.reads[0]?.raw===source;
        const item={action:{kind:'rcl',reg,source,operand,lead},...compact(next)};
        attempts.push({...item,match});if(next.held&&match)positive.push({...item,next});
      }
    }
    for(const kind of ['cx','swap','enter','lastx','nop'])for(const lead of [0,6,12,18,24]) {
      const next=keyCall(cur,0,lead,{kind,preserved:held}),item={action:{kind,operand:0,lead},...compact(next)};
      attempts.push(item);if(next.held&&next.ended)positive.push({...item,next});
    }
    return{positive,attempts};
  };
  const first=candidates(current);
  return{prefixSteps,adapter,positive:first.positive.map(({next,...v})=>v),
    completedWithoutBE:first.attempts.filter(v=>v.held&&!v.ended),
    boundary:'Ordinary reserve ledger only. Source-derived actions on accepted FFF/P7 plus documented marker push/pop/formatter functions; no native route/full K1/K2.'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run,held,compact};
