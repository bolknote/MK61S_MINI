#!/usr/bin/env node
'use strict';
// Finite, source-directed ROM map at the measured U=SECOND/P10=FIRST
// frontier. Vary only the accepted 9C word/calendar, not calculator states
// or keyboard sequences. Candidates are CONDITIONAL PRIMARY-ONLY paths.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const model=require('./cache-bc-head93-primary-word-model.cjs');
const {pagesAt,call,auditConnected}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const numeric=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const ordinary=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000',F='0000F0000000';
function run({log=true}={}) {
  const data=prepare({proof:true,phase:'yku',secondPhase:'p9-source-write'});
  auditConnected(data,['packet-second-open4','packet-second-open5','packet-second-write']);
  const rec=data.windows['packet-second-open5'][0],pages=pagesAt(data,rec),template=rec.fullBefore.ik1302;
  assert.equal(numeric(pages[10]),FIRST);assert.equal(numeric(pages[3]),SECOND);
  const entries=names.map((_,j)=>j).filter(j=>pages[j][31]===15?pages[j][34]>=1:pages[j][34]>=7);
  const ports=names.map((_,j)=>({reg:(j+12)%15,value:ordinary(pages[j])}));
  const table=[];
  for(const entry of entries)for(const type of [4,6])for(const {reg,value} of ports) {
    const result=call(pages,template,reg,type,entry,undefined,{
      preserveP10:false,allowedSources:[ZERO,F,FIRST,SECOND]});
    if(!result)continue;
    const held=numeric(result.pages[10])===FIRST;
    // Endpoint preservation alone is NOT sufficient: rerun with an invariant
    // after EVERY primary word to reject transient destructive frames.
    const continuous=call(pages,template,reg,type,entry,undefined,{
      allowedSources:[ZERO,F,FIRST,SECOND],preserved:p=>numeric(p[10])===FIRST});
    table.push({entry:names[entry],type,reg,operand:result.operand,source:result.source,ordinaryPortBefore:value,
      writers:result.writers,P10heldAtEnd:held,P10heldEveryWord:!!continuous,
      P7:numeric(result.pages[7]),P9:numeric(result.pages[9]),
      markers:names.filter((_,j)=>result.pages[j][22]===15),
      candidate:!!continuous&&[7,9].some(j=>numeric(result.pages[j])===SECOND)});
  }
  const simple=[];
  for(const label of ['packet-clean-enter','packet-clean-lastx','packet-second-write']) {
    const v=data.windows[label].find(x=>x.ip===0x9C);
    const keyX=v.keysX[0],keyY=v.keysY[0];
    for(const entry of entries) {
      const next=pages.map(p=>p.slice());let a=model.clone(v.fullBefore.ik1302),here=entry,held=true,ended=false;
      a.m=next[here].slice();const writers=[];
      for(let k=0;k<500;k++) {
        const ip=model.ip(a);if(ip===0xBE){ended=true;break;}
        if([0xE7,0xA8,0xE9,0xBC].includes(ip))writers.push([ip,names[here]]);
        const x=model.step(a,keyX,keyY,next[(here+1)%15]);next[here]=x.out;a=x.state;here=(here+1)%15;
        if(numeric(next[10])!==FIRST)held=false;
      }
      simple.push({label,entry:names[entry],ended,P10heldEveryWord:held,writers,
        P7:numeric(next[7]),P9:numeric(next[9]),
        candidate:ended&&held&&[7,9].some(j=>numeric(next[j])===SECOND)});
    }
  }
  const result={entries:entries.map(j=>names[j]),table,simple,
    candidates:[...table,...simple].filter(x=>x.candidate),
    boundary:'finite accepted9C PRIMARY map; template/native entry compatibility, ALL5, return/read unproved'};
  if(log)console.log(JSON.stringify(result));return {data,result};
}
function derivedShift(data) {
  const rec=data.windows['packet-second-open5'][0],template=rec.fullBefore.ik1302;
  let pages=pagesAt(data,rec);const path=[];
  for(const reg of [8,8,8,13]) {
    const result=call(pages,template,reg,6,12,undefined,{
      allowedSources:[ZERO,F,FIRST,SECOND],preserved:p=>numeric(p[10])===FIRST});
    if(!result)return {path,failedAtReg:reg,boundary:'conditional derived transfers; invariant rejected'};
    path.push({reg,operand:result.operand,root:result.root,writers:result.writers,
      markers:names.filter((_,j)=>result.pages[j][22]===15),
      words:Object.fromEntries(names.map((n,j)=>[n,numeric(result.pages[j])]))});
    pages=result.pages;
  }
  const erase=[];
  for(const reg of [6,7]) {
    const result=call(pages,template,reg,4,12,undefined,{
      allowedSources:[ZERO,F,FIRST,SECOND],
      preserved:p=>numeric(p[10])===FIRST&&numeric(p[7])===SECOND});
    if(!result){erase.push({reg,failed:true});break;}
    const actual=ordinary(result.pages[(reg+3)%15]);
    erase.push({reg,operand:result.operand,root:result.root,actual,writers:result.writers,
      numericalCopyErased:actual===ZERO});
    pages=result.pages;
  }
  // Remove U/F with an actual zero source from the now-erased realR7.
  // If both hidden slots survive, STORE is a NON-shifting candidate reader:
  // its EE source would become P7 after the first remaining V/F root.
  const reader=[],firstReaderFrontier=[];
  const opened=call(pages,template,7,6,12,undefined,{
    allowedSources:[ZERO,F,FIRST,SECOND],
    preserved:p=>numeric(p[10])===FIRST&&numeric(p[7])===SECOND});
  if(opened) {
    reader.push({kind:'zero-read7',operand:opened.operand,writers:opened.writers,
      markers:names.filter((_,j)=>opened.pages[j][22]===15),
      P9:numeric(opened.pages[9])});
    const output=call(opened.pages,template,6,4,12,undefined,{
      allowedSources:[ZERO,F,FIRST,SECOND],
      preserved:p=>numeric(p[10])===FIRST&&numeric(p[7])===SECOND});
    reader.push(output?{kind:'STORE-output6',operand:output.operand,writers:output.writers,
      actual:ordinary(output.pages[9]),readsSecond:ordinary(output.pages[9])===SECOND}:
      {kind:'STORE-output6',failed:true});
    if(output&&ordinary(output.pages[9])===SECOND) {
      let current=output.pages;
      for(const reg of [7,7,0,0,0]) {
        const moved=call(current,template,reg,6,12,undefined,{
          allowedSources:[ZERO,F,FIRST,SECOND],
          preserved:p=>numeric(p[10])===FIRST&&numeric(p[7])===SECOND&&ordinary(p[9])===SECOND});
        if(!moved){firstReaderFrontier.push({reg,failed:true});break;}
        firstReaderFrontier.push({reg,operand:moved.operand,writers:moved.writers,
          markers:names.filter((_,j)=>moved.pages[j][22]===15)});
        current=moved.pages;
        if(names.filter((_,j)=>current[j][22]===15).join(',')==='P8')break;
      }
    }
  } else reader.push({kind:'zero-read7',failed:true});
  return {path,P7second:numeric(pages[7])===SECOND,P9second:numeric(pages[9])===SECOND,
    erase,reader,firstReaderFrontier,
    boundary:'derived PRIMARY plan only; native compatibility, clean return, readers not yet checked'};
}
if(require.main===module) {
  const v=run({log:!process.argv.includes('--derived')});
  if(process.argv.includes('--derived'))console.log(JSON.stringify(derivedShift(v.data)));
}
module.exports={run,derivedShift};
