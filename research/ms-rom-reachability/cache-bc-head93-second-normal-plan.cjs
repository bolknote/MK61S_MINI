#!/usr/bin/env node
'use strict';
// Source-directed return to ordinary aux0 geometry while BOTH Ms words hold.
// Whole PRIMARY key/release calculation; no model states enter a calculator.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-second-first-native.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const numeric=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const ordinary=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000',F='0000F0000000';
const markers=p=>names.filter((_,j)=>p[j][22]===15);
const holds=(p,word)=>numeric(p[10])===FIRST&&(numeric(p[7])===SECOND||numeric(p[8])===SECOND||
  (word?.ip===0xA8&&word.writtenWord==='P7'&&
   word.state.r.slice(0,36).filter((_,j)=>j%3===0).reverse().map(n=>n.toString(16).toUpperCase()).join('')===SECOND));
const entries=p=>names.map((_,j)=>j).filter(j=>p[j][31]===15?p[j][34]>=1:p[j][34]>=7);
function auditPositive() {
  const data=require('./cache-bc-head93-second-normal-native.cjs').run({proof:true});
  const endpoint=data.nativeEndpoints['packet-second-first-output'];
  let current={state:endpoint.fullBefore.ik1302,pages:pagesAt(data,endpoint),here:names.indexOf(endpoint.numericOwner[0].split(':')[1])};
  const protocol=[['clear',0,'cx'],['erase6',9,'store'],['erase7',10,'store'],
    ['aux0',6],['port5',8,'store'],['Y',8],['X1',11],['relocate',14],['adapter',4],
    ...Array.from({length:4},(_,i)=>['flush'+(i+1),4]),['port5-zero',5,'store']];
  let words=0;
  for(const [suffix,operand,kind='rcl'] of protocol) {
    const next=keyCall(current,operand,0,{kind,preserved:holds}),native=data.nativeEndpoints['packet-normal-'+suffix];
    assert.ok(next.held,suffix);
    assert.equal(endpoint.word+words+next.words,native.word,suffix+' complete native key/idle schedule');
    for(const field of ['r','m','st','s','s1','l','t','carry'])assert.deepEqual(next.state[field],native.fullBefore.ik1302[field],suffix+'/'+field);
    assert.deepEqual(next.pages,pagesAt(data,native),suffix+' all15 primary ring pages');
    current=next;words+=next.words;
  }
  assert.equal(words,226800);assert.deepEqual(markers(current.pages),['aux0']);
  assert.equal(numeric(current.pages[8]),SECOND);assert.equal(numeric(current.pages[10]),FIRST);
  console.log('PASS EXACT PRIMARY',words,'whole key/idle words,14 native endpoint checks/all primary fields+15 pages; '
    +'SECOND P7->A(one word)->P8, FIRST P10 held, ordinary numerical copies0. '
    +'NOT ALL5 and does not calculate third-chip arithmetic.');
}
function run() {
  const data=prepare({proof:true,readFirst:true}),endpoint=data.nativeEndpoints['packet-second-first-output'];
  let current={state:endpoint.fullBefore.ik1302,pages:pagesAt(data,endpoint),here:names.indexOf(endpoint.numericOwner[0].split(':')[1])};
  const template=data.windows['packet-second-first-V'][0].fullBefore.ik1302,path=[];
  const report=()=>({markers:markers(current.pages),M2:Object.fromEntries(names.map((n,j)=>[n,numeric(current.pages[j])])),
    M1:Array.from({length:15},(_,reg)=>ordinary(current.pages[(reg+3)%15]))});
  function action(target) {
    if(target.header) {
      for(const operand of [4,0])for(const lead of [0,6,12,18,24]) {
        const next=keyCall(current,operand,lead,{preserved:holds});
        if(!next.held||!next.writers.some(([ip,n])=>ip===0xA3&&n===target.header))continue;
        current=next;path.push({target,kind:'rcl',operand,lead,reads:next.reads,writers:next.writers,markers:markers(next.pages)});
        return true;
      }
      path.push({target,failed:true});return false;
    }
    const kind=target.kind||'rcl',type=kind==='store'?4:6;
    const ops=kind==='cx'?[0]:[...new Set(entries(current.pages).map(entry=>sourceRoot(current.pages,template,type,entry))
      .filter(x=>x!==null).map(root=>(target.reg+11-root+30)%15))];
    const rejected=[];
    for(const operand of ops)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{kind,preserved:holds});
      rejected.push({operand,lead,held:next.held,ended:next.ended,decoded:next.firstDecode?.owner,
        reads:next.reads,writers:next.writers,markers:markers(next.pages)});
      if(!next.held||!next.ended)continue;
      if(kind==='rcl'&&(next.reads[0]?.reg!==target.reg||next.reads[0]?.raw!==target.source))continue;
      if(target.frame&&next.writers.find(([ip])=>ip===0xE7)?.[1]!==target.frame)continue;
      if(kind==='store'&&(ordinary(next.pages[(target.reg+3)%15])!==target.source||
        next.writers.find(([ip])=>ip===0xD4)?.[1]!==names[(target.reg+3)%15]))continue;
      if(target.clear&&next.pages[names.indexOf(target.clear)][22]===15)continue;
      current=next;path.push({target,kind,operand,lead,reads:next.reads,writers:next.writers,markers:markers(next.pages)});
      return true;
    }
    path.push({target,failed:true,operands:ops,rejected});return false;
  }
    const steps=[{kind:'cx'}, {kind:'store',reg:6,source:ZERO},{kind:'store',reg:7,source:ZERO},
    {reg:3,source:F,frame:'aux0'}, {kind:'store',reg:5,source:F},
    {reg:5,source:F,frame:'Y'},{reg:8,source:F,frame:'X1'},
    {reg:11,source:ZERO,frame:'W',relocation:'P7->A->P8'},
    {header:'aux1'},
    ...Array.from({length:3},()=>({reg:4,source:ZERO,frame:'Y'})),
    {kind:'cx',clear:'W'},{reg:4,source:ZERO,frame:'Y'},
    {kind:'store',reg:5,source:ZERO}];
  for(const step of steps) {
    if(step.clear&&current.pages[names.indexOf(step.clear)][22]!==15)continue;
    if(!action(step))break;
    if(markers(current.pages).join(',')==='aux0') {
      if(ordinary(current.pages[8])===F)action({kind:'store',reg:5,source:ZERO});
      break;
    }
  }
  console.log(JSON.stringify({path,endpoint:report(),canonical:markers(current.pages).join(',')==='aux0',
    boundary:'whole PRIMARY source/key-calendar planning; native full5/ordinary arithmetic/re-read remain unproved'}));
}
if(require.main===module)process.argv.includes('--positive')?auditPositive():run();
module.exports={run,auditPositive};
