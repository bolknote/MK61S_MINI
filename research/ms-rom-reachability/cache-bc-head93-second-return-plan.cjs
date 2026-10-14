#!/usr/bin/env node
'use strict';
// ROM/source-directed continuation from the genuine two-slot P7 reader.
// Conditional PRIMARY calculations only; no model states enter a calculator.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-second-first-native.cjs');
const {pagesAt,call,auditConnected}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const model=require('./cache-bc-head93-primary-word-model.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const numeric=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const ordinary=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000',F='0000F0000000';
const markers=p=>names.filter((_,j)=>p[j][22]===15);
const entries=p=>names.map((_,j)=>j).filter(j=>p[j][31]===15?p[j][34]>=1:p[j][34]>=7);
const hold=p=>numeric(p[7])===SECOND&&numeric(p[10])===FIRST&&ordinary(p[9])===SECOND;
const report=p=>({markers:markers(p),words:Object.fromEntries(names.map((n,j)=>[n,numeric(p[j])])),
  registers:Object.fromEntries(names.map((_,j)=>[(j+12)%15,ordinary(p[j])]))});
function lastX(pages,record,entry=12) {
  const next=pages.map(p=>p.slice());let a=model.clone(record.fullBefore.ik1302),here=entry;
  a.m=next[here].slice();const readers=[],writers=[];
  for(let i=0;i<500;i++) {
    const ip=model.ip(a);
    if(ip===0xBE)return {pages:next,readers,writers};
    if(ip===0xEE)readers.push({word:names[here],raw:numeric(next[here])});
    if([0xE7,0xA8,0xE9,0xD4].includes(ip))writers.push([ip,names[here]]);
    const x=model.step(a,record.keysX[0],record.keysY[0],next[(here+1)%15]);
    next[here]=x.out;a=x.state;here=(here+1)%15;
    if(!hold(next))return null;
  }
  return null;
}
function run({log=true}={}) {
  const data=prepare({proof:true});
  auditConnected(data,['packet-second-read-output','packet-second-first1','packet-second-first2','packet-second-first3']);
  const firstAttempt=data.windows['packet-second-first1'][0];
  const template=firstAttempt.fullBefore.ik1302;
  let pages=pagesAt(data,firstAttempt);
  assert.ok(hold(pages));assert.deepEqual(markers(pages),['Z','V','W','P8','Y']);
  const path=[];
  // Move V/W out in X1..W, then remove Y in aux0..Y. Restore aux0/F
  // with R3/F so that four Y..X1 pushes can remove Z/T/X1 without P7.
  const regs=[7,7,0,3,4,4,4,4,0,0,0];
  for(const reg of regs) {
    const accepted=entries(pages);
    if(!accepted.length){const result={path,frontier:report(pages),failedReg:reg,
      boundary:'no accepted header in this PRIMARY model endpoint; full idle/controller needed'};
      if(log)console.log(JSON.stringify(result));return {data,result};}
    const entry=accepted.includes(12)?12:accepted[0];
    const next=call(pages,template,reg,6,entry,undefined,{
      allowedSources:[ZERO,F,SECOND],preserved:hold});
    if(!next){const result={path,failedReg:reg,frontier:report(pages),
      boundary:'conditional primary transfer rejected; not a native no-go'};
      if(log)console.log(JSON.stringify(result));return {data,result};}
    path.push({reg,operand:next.operand,root:next.root,entry:names[entry],writers:next.writers,markers:markers(next.pages)});
    pages=next.pages;
    if(path.length===3) {
      const entry=entries(pages)[0];
      const early=entry===undefined?null:lastX(pages,data.windows['packet-reopen-lastx'][0],entry);
      if(early&&early.readers[0]?.word==='P10') {
        const stored=call(early.pages,template,7,4,entries(early.pages)[0],undefined,{
          allowedSources:[ZERO,F,FIRST,SECOND],preserved:hold});
        const result={path,earlyFirst:{entry:names[entry],readers:early.readers,writers:early.writers,endpoint:report(early.pages)},
          stored:stored?{operand:stored.operand,R7:ordinary(stored.pages[10]),writers:stored.writers}:null,
          boundary:'conditional first read before full marker cleanup; native phase/prefix/read not proved'};
        if(log)console.log(JSON.stringify(result));return {data,result};
      }
    }
    if(markers(pages).join(',')==='P8')break;
  }
  const first=markers(pages).join(',')==='P8'?lastX(pages,data.windows['packet-reopen-lastx'][0],entries(pages)[0]):null;
  const stored=first?call(first.pages,template,7,4,entries(first.pages)[0],undefined,{
    allowedSources:[ZERO,F,FIRST,SECOND],preserved:hold}):null;
  const result={path,frontier:report(pages),
    first:first?{readers:first.readers,writers:first.writers,endpoint:report(first.pages)}:null,
    stored:stored?{operand:stored.operand,writers:stored.writers,R7:ordinary(stored.pages[10]),endpoint:report(stored.pages)}:null,
    boundary:'conditional source/marker ROM calculation; fresh native keys/ALL5 and clean normal return remain unproved'};
  if(log)console.log(JSON.stringify(result));return {data,result};
}
if(require.main===module)run();
module.exports={run,lastX};
