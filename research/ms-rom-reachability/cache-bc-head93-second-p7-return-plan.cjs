#!/usr/bin/env node
'use strict';
// Normal-return alternative: never move SECOND away from P7. All targets
// are selected by the existing exact ROM reader/frame geometry, not keys.
// Whole PRIMARY key/release planning only; no reference state imports.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=(p,l=1)=>p.filter((_,j)=>j%3===l).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const marks=p=>names.filter((_,j)=>p[j][22]===15);
const FIRST='007012345678',SECOND='007024681357',F='0000F0000000',ZERO='000000000000';
const holds=p=>raw(p[7])===SECOND&&raw(p[10])===FIRST;
function compact(v){return{held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,
  writers:v.writers,markers:marks(v.pages),P7:raw(v.pages[7]),P10:raw(v.pages[10])};}
function run(file) {
  const d=JSON.parse(fs.readFileSync(file,'utf8'));
  const start=process.argv.find(v=>v.startsWith('--entry='))?.slice(8)||'packet-normal-X1';
  const entry=d.endpoints[start];
  assert.ok(entry,'capture must include the actual pre-relocation checkpoint');
  let current={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const template=d.windows['packet-normal-X1'].find(v=>v.ip===0x9C&&
    (v.fullBefore.ik1302.m[31]===15?v.fullBefore.ik1302.m[34]>=1:v.fullBefore.ik1302.m[34]>=7)).fullBefore.ik1302;
  assert.ok(holds(current.pages));
  const path=[];
  function apply(target) {
    if(target.header) {
      const rejected=[];
      for(const operand of [8,4,0])for(const lead of [0,6,12,18,24]) {
        const next=keyCall(current,operand,lead,{preserved:holds});
        rejected.push({operand,lead,...compact(next)});
        if(!next.held||!next.writers.some(([ip,n])=>ip===0xA3&&n===target.header))continue;
        current=next;path.push({target,operand,lead,...compact(next)});return true;
      }
      path.push({target,failed:true,rejected});return false;
    }
    const kind=target.kind||'rcl';
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const ops=kind==='cx'?[0]:[...new Set(entries.map(j=>sourceRoot(current.pages,template,kind==='store'?4:6,j))
      .filter(x=>x!==null).map(root=>(target.reg+11-root+30)%15))];
    const rejected=[];
    for(const operand of ops)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{kind,preserved:holds});
      rejected.push({operand,lead,...compact(next)});
      if(!next.held||!next.ended)continue;
      if(target.clear&&next.pages[names.indexOf(target.clear)][22]===15)continue;
      if(kind==='rcl'&&(next.reads[0]?.reg!==target.reg||next.reads[0]?.raw!==target.source||
        (target.frame&&next.writers.find(([ip])=>ip===0xE7)?.[1]!==target.frame)))continue;
      if(kind==='store'&&(raw(next.pages[(target.reg+3)%15],0)!==target.source||
        next.writers.find(([ip])=>ip===0xD4)?.[1]!==names[(target.reg+3)%15]))continue;
      current=next;path.push({target,operand,lead,...compact(next)});return true;
    }
    path.push({target,failed:true,ops,rejected});return false;
  }
  const steps=[...Array.from({length:3},()=>({reg:7,source:ZERO,frame:'X1'})),
    {kind:'cx',clear:'P8'},
    {header:'aux1'},
    {reg:8,source:F,frame:'X1'},
    {kind:'cx',clear:'W'},
    ...Array.from({length:4},()=>({reg:4,source:ZERO,frame:'Y'})),
    {kind:'store',reg:5,source:ZERO}];
  for(const target of steps) {
    if(target.clear&&current.pages[names.indexOf(target.clear)][22]!==15)continue;
    if(!apply(target))break;
    if(marks(current.pages).join(',')==='aux0') {
      if(raw(current.pages[8],0)===F)apply({kind:'store',reg:5,source:ZERO});
      break;
    }
  }
  console.log(JSON.stringify({start,path,canonical:marks(current.pages).join(',')==='aux0',
    final:{markers:marks(current.pages),P7:raw(current.pages[7]),P10:raw(current.pages[10]),
      ordinary:current.pages.map(p=>raw(p,0))},
    boundary:'strict P7/P10 PRIMARY return hypotheses only; native ordinary math/read/repeat required'}));
}
if(require.main===module)run(process.argv[2]);
function auditNative(data) {
  const entry=data.nativeEndpoints['packet-normal-X1'];
  let current={state:entry.fullBefore.ik1302,pages:pagesAt(data,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const protocol=[...Array.from({length:3},(_,i)=>['retain-shift'+(i+1),10,0,'rcl']),
    ['retain-clearP8',0,12,'cx'],['retain-header',8,6,'rcl'],['retain-X1',5,0,'rcl'],
    ...Array.from({length:4},(_,i)=>['retain-flush'+(i+1),4,0,'rcl']),['port5-zero',5,0,'store']];
  let words=0;
  for(const [suffix,operand,lead,kind] of protocol) {
    const next=keyCall(current,operand,lead,{kind,preserved:holds});
    const native=data.nativeEndpoints['packet-normal-'+suffix];
    assert.ok(next.held,suffix+' P7/P10 before/after every primary word');
    assert.equal(entry.word+words+next.words,native.word,suffix+' entire key/idle calendar');
    for(const field of ['r','m','st','s','s1','l','t','carry'])
      assert.deepEqual(next.state[field],native.fullBefore.ik1302[field],suffix+'/'+field);
    assert.deepEqual(next.pages,pagesAt(data,native),suffix+' all15 ring pages/all3 lanes');
    assert.equal(names[next.here],native.numericOwner[0].split(':')[1]);
    current=next;words+=next.words;
  }
  assert.equal(words,176460);assert.deepEqual(marks(current.pages),['aux0']);
  assert.equal(raw(current.pages[8],0),ZERO);
  console.log('PASS EXACT PRIMARY',words,'whole fixed key/release/idle words,11 genuine endpoint '
    +'checks/all primary fields+15 three-lane pages; P7/P10 held, no repair. NOT ALL5.');
}
module.exports={run,auditNative};
