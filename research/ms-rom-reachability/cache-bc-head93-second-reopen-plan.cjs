#!/usr/bin/env node
'use strict';
// Source-selected reverse reader frontier from genuine normal arithmetic.
// P8 now contains SECOND; creating P8/F would destroy it, so use Q/F's
// LastX address P8 instead. Conditional PRIMARY full-key planning only.
const {run:prepare}=require('./cache-bc-head93-second-normal-native.cjs');
const assert=require('node:assert/strict');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const reg=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',F='0000F0000000',ZERO='000000000000';
const marks=p=>names.filter((_,j)=>p[j][22]===15);
const holds=p=>raw(p[8])===SECOND&&raw(p[10])===FIRST;
function run() {
  const data=prepare({proof:true,math:true}),endpoint=data.nativeEndpoints['packet-normal-preclear4'];
  if(process.argv.includes('--audit-enter')) {
    const start=data.nativeEndpoints['packet-normal-two'],end=data.nativeEndpoints['packet-normal-enter'];
    const next=keyCall({state:start.fullBefore.ik1302,pages:pagesAt(data,start),
      here:names.indexOf(start.numericOwner[0].split(':')[1])},0,0,{kind:'enter',preserved:holds});
    assert.ok(next.held&&next.ended);
    assert.equal(start.word+next.words,end.word);
    for(const field of ['r','m','st','s','s1','l','t','carry'])
      assert.deepEqual(next.state[field],end.fullBefore.ik1302[field],field);
    assert.deepEqual(next.pages,pagesAt(data,end));
    assert.equal(names[next.here],end.numericOwner[0].split(':')[1]);
    console.log('PASS exact PRIMARY ENTER key/release/idle schedule',next.words,
      'words, all primary fields+15 three-lane pages agree with genuine normal ENTER. NOT ALL5/arbitrary ENTER contract.');
    return;
  }
  const template=data.windows['packet-normal-flush1'].find(v=>v.ip===0x9C&&v.fullBefore.ik1302.m[31]===15).fullBefore.ik1302;
  let current={state:endpoint.fullBefore.ik1302,pages:pagesAt(data,endpoint),here:names.indexOf(endpoint.numericOwner[0].split(':')[1])};
  const path=[];
  for(const target of [...Array.from({length:4},()=>({reg:3,frame:'Y',source:F})),
    ...Array.from({length:2},()=>({reg:7,frame:'X1',source:ZERO})),
    {kind:'cx',clear:'Y'},
    ...(process.argv.includes('--clear-front')||process.argv.includes('--swap')?Array.from({length:3},()=>({reg:4,frame:'Y',source:ZERO})):[]),
    ...(process.argv.includes('--front-one')?[{reg:4,frame:'Y',source:ZERO}]:[]),
    ...(process.argv.includes('--swap')?[{kind:'swap'}]:
      Array.from({length:2},()=>process.argv.includes('--enter')?{kind:'enter',frame:'U'}:
        {reg:10,frame:process.argv.includes('--front-one')?'V':'U',source:ZERO}))]) {
    if(target.header) {
      let chosen=null;
      header:for(const operand of [4,0])for(const lead of [0,6,12,18,24]) {
        const next=keyCall(current,operand,lead,{preserved:holds});
        if(next.held&&next.writers.some(([ip,n])=>ip===0xA3&&n===target.header)){
          chosen={operand,lead,next};break header;
        }
      }
      if(!chosen){path.push({target,failed:true});break;}
      current=chosen.next;path.push({target,operand:chosen.operand,lead:chosen.lead,writers:current.writers,markers:marks(current.pages)});
      continue;
    }
    const kind=target.kind||'rcl',type=kind==='store'?4:6;
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const ops=['cx','enter','swap'].includes(kind)?[0]:[...new Set(entries.map(j=>sourceRoot(current.pages,template,type,j))
      .filter(x=>x!==null).map(root=>(target.reg+11-root+30)%15))];
    let chosen=null;const rejected=[];
    find:for(const operand of ops)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{kind,preserved:holds});
      rejected.push({operand,lead,held:next.held,ended:next.ended,reads:next.reads,
        numericReads:next.numericReads,writers:next.writers,markers:marks(next.pages),
        P7:raw(next.pages[7]),P8:raw(next.pages[8]),P10:raw(next.pages[10])});
      if(!next.held||!next.ended)continue;
      if(target.clear&&next.pages[names.indexOf(target.clear)][22]===15)continue;
      if(kind==='rcl'&&(next.reads[0]?.reg!==target.reg||next.reads[0]?.raw!==target.source||next.writers.find(([ip])=>ip===0xE7)?.[1]!==target.frame))continue;
      if(kind==='enter'&&next.writers.find(([ip])=>ip===0xE7)?.[1]!==target.frame)continue;
      if(kind==='store'&&(reg(next.pages[13])!==F||next.writers.find(([ip])=>ip===0xD4)?.[1]!=='X'))continue;
      chosen={operand,lead,next};break find;
    }
    if(!chosen){path.push({target,ops,failed:true,rejected});break;}
    current=chosen.next;path.push({target,operand:chosen.operand,lead:chosen.lead,markers:marks(current.pages),writers:current.writers});
  }
  if(current.pages[6][22]===15) {
    header:for(const operand of [4,0])for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{preserved:holds});
      if(next.held&&next.writers.some(([ip,n])=>ip===0xA3&&['Z','T'].includes(n))) {
        path.push({target:'Z/T header adapter',operand,lead,writers:next.writers,markers:marks(next.pages)});
        current=next;break header;
      }
    }
  }
  const readers=[],readerDiagnostics=[];
  for(const lead of [0,6,12,18,24]) {
    const next=keyCall(current,0,lead,{kind:'lastx',preserved:holds});
    readerDiagnostics.push({lead,held:next.held,ended:next.ended,numericReads:next.numericReads,
      writers:next.writers,markers:marks(next.pages),P8:raw(next.pages[8]),P10:raw(next.pages[10])});
    if(next.held&&next.ended&&next.numericReads[0]?.word==='P8'&&next.numericReads[0]?.raw===SECOND)
      readers.push({lead,numericReads:next.numericReads,writers:next.writers,markers:marks(next.pages)});
  }
  console.log(JSON.stringify({path,readers,readerDiagnostics,frontier:marks(current.pages),
    boundary:'source-directed PRIMARY reverse-reader hypotheses only, not native retrieval/repeat; ordinary math prefix is genuine full5'}));
}
if(require.main===module)run();
module.exports={run};
