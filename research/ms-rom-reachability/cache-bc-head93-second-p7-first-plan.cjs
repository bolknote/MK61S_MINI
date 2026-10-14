#!/usr/bin/env node
'use strict';
// After genuine post-math P7 retrieval, build the old P8/P10 reader using
// safe visible/X1 frames. R6 is an OUTPUT of P7, never a P10 source.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=(p,l=1)=>p.filter((_,j)=>j%3===l).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',F='0000F0000000',ZERO='000000000000';
const marks=p=>names.filter((_,j)=>p[j][22]===15);
const holds=p=>raw(p[7])===SECOND&&raw(p[10])===FIRST&&raw(p[9],0)===SECOND;
function summary(v){return{held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,
  writers:v.writers,markers:marks(v.pages),P7:raw(v.pages[7]),P10:raw(v.pages[10])};}
function run(file) {
  const d=JSON.parse(fs.readFileSync(file,'utf8'));assert.equal(d.metadata.profile,'p7-normal-retain-read');
  const entry=d.endpoints['packet-p7-read-output'];
  let current={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const third=process.argv.includes('--third-p9')?'950013579246':null;
  if(third) {
    const values=Array.from(third).reverse().map(n=>parseInt(n,16));
    for(let j=0;j<12;j++)current.pages[9][1+3*j]=values[j];
    if(current.here===9)current.state={...current.state,m:current.pages[9].slice()};
    console.log('CONDITIONAL INITIAL DATA ONLY: physicalP9=1.3579246E-50, all12 fields; no device import/other edits.');
  }
  const preserved=third?p=>holds(p)&&raw(p[9])===third:holds;
  const template=d.windows['packet-p7-read-output'].find(v=>v.ip===0x9C&&
    (v.fullBefore.ik1302.m[31]===15?v.fullBefore.ik1302.m[34]>=1:v.fullBefore.ik1302.m[34]>=7)).fullBefore.ik1302;
  assert.ok(holds(current.pages));const path=[];
  const steps=[...Array.from({length:3},()=>({reg:3,source:F,frame:'Y'})),
    {reg:10,source:ZERO,frame:'U'},
    ...Array.from({length:2},()=>({reg:7,source:ZERO,frame:'X1'})),
    {reg:3,source:F,frame:'aux0'},
    ...Array.from({length:2},()=>({reg:4,source:ZERO,frame:'Y'})),
    {kind:'cx',clear:'W'},{reg:4,source:ZERO,frame:'Y'},
    ...Array.from({length:4},()=>({reg:2,source:ZERO,frame:'aux0'})),
    {kind:'lastx',numericSource:'P10'}, {kind:'store',reg:7,source:FIRST}];
  for(const target of steps) {
    if(target.clear&&current.pages[names.indexOf(target.clear)][22]!==15)continue;
    const kind=target.kind||'rcl',type=kind==='store'?4:6;
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const ops=['cx','lastx'].includes(kind)?[0]:[...new Set(entries.map(j=>sourceRoot(current.pages,template,type,j))
      .filter(x=>x!==null).map(root=>(target.reg+11-root+30)%15))];
    const rejected=[];let chosen=null;
    candidates:for(const operand of ops)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{kind,preserved});
      rejected.push({operand,lead,...summary(next)});
      if(!next.held||!next.ended)continue;
      if(target.clear&&next.pages[names.indexOf(target.clear)][22]===15)continue;
      if(kind==='rcl'&&(next.reads[0]?.reg!==target.reg||next.reads[0]?.raw!==target.source||
        next.writers.find(([ip])=>ip===0xE7)?.[1]!==target.frame))continue;
      if(target.numericSource&&(next.numericReads[0]?.word!==target.numericSource||next.numericReads[0]?.raw!==FIRST))continue;
      if(kind==='store'&&(raw(next.pages[(target.reg+3)%15],0)!==target.source||
        next.writers.find(([ip])=>ip===0xD4)?.[1]!==names[(target.reg+3)%15]))continue;
      chosen={operand,lead,next};break candidates;
    }
    if(!chosen){path.push({target,failed:true,ops,rejected});break;}
    current=chosen.next;path.push({target,operand:chosen.operand,lead:chosen.lead,...summary(current)});
  }
  console.log(JSON.stringify({path,frontier:marks(current.pages),
    R6:raw(current.pages[9],0),R7:raw(current.pages[10],0),P9:raw(current.pages[9]),third,
    boundary:'PRIMARY post-math P10 reader hypotheses; native/all5/repeat/full K1/K2 still required'}));
}
if(require.main===module)run(process.argv[2]);
module.exports={run};
