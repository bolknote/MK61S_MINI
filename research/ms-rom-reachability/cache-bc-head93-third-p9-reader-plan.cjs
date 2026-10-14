#!/usr/bin/env node
'use strict';
// Model-only P9 input tests for a non-shifting STORE reader. The number is
// NOT keyboard-written by this probe. Preserve all THREE at every word.
const fs=require('node:fs');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=(p,l=1)=>p.filter((_,j)=>j%3===l).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',THIRD='950013579246',F='0000F0000000',ZERO='000000000000';
const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),entry=d.endpoints['packet-p7-read-output'];
const template=d.windows['packet-p7-read-output'].find(v=>v.ip===0x9C).fullBefore.ik1302;
const holds=p=>raw(p[7])===SECOND&&raw(p[9])===THIRD&&raw(p[10])===FIRST;
const compact=v=>({held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,writers:v.writers,
  markers:names.filter((_,j)=>v.pages[j][22]===15),P9:raw(v.pages[9])});
function run(seeds) {
  let current={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  for(let j=0;j<12;j++)current.pages[9][1+3*j]=parseInt(THIRD[11-j],16);
  if(current.here===9)current.state={...current.state,m:current.pages[9].slice()};
  const steps=[...Array.from({length:seeds},()=>({reg:3,source:F,frame:'Y'})),
    {reg:10,source:ZERO,frame:'U'},{reg:10,source:ZERO,frame:'U'},
    ...Array.from({length:3},()=>({reg:5,source:ZERO,frame:'Y'})),{kind:'store',reg:4,source:THIRD}],path=[];
  for(const target of steps) {
    const kind=target.kind||'rcl';
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const ops=[...new Set(entries.map(j=>sourceRoot(current.pages,template,kind==='store'?4:6,j)).filter(x=>x!==null)
      .map(root=>(target.reg+11-root+30)%15))];
    let chosen=null;const rejected=[];
    candidates:for(const operand of ops)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{kind,preserved:holds});rejected.push({operand,lead,...compact(next)});
      if(!next.held||!next.ended)continue;
      if(kind==='rcl'&&(next.reads[0]?.reg!==target.reg||next.reads[0]?.raw!==target.source||next.writers.find(([ip])=>ip===0xE7)?.[1]!==target.frame))continue;
      if(kind==='store'&&raw(next.pages[(target.reg+3)%15],0)!==target.source)continue;
      chosen={operand,lead,next};break candidates;
    }
    if(!chosen){path.push({target,failed:true,rejected});break;}
    current=chosen.next;path.push({target,operand:chosen.operand,lead:chosen.lead,...compact(current)});
  }
  return {seeds,path,R4:raw(current.pages[7],0),P9:raw(current.pages[9])};
}
console.log(JSON.stringify({cases:[run(2),run(3)],boundary:'INITIAL P9 DATA/PRIMARY candidates only; not a native third writer/reader/K1/K2'}));
