#!/usr/bin/env node
'use strict';
// Derive a late single P9 writer by moving V/F->W/F->Q/F while keeping
// THIRD in visibleY. Initial ordinaryR4 source is DATA ONLY in this model.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=(p,l=1)=>p.filter((_,j)=>j%3===l).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',THIRD='950013579246',F='0000F0000000',ZERO='000000000000';
const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const entry=d.endpoints['packet-p7-read-output'];
let current={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
for(let j=0;j<12;j++)current.pages[7][3*j]=parseInt(THIRD[11-j],16);
const relocating=process.argv.includes('--relocate-first');
if(relocating)for(let j=0;j<12;j++)current.pages[11][3*j]=parseInt(THIRD[11-j],16);
if(current.here===7)current.state={...current.state,m:current.pages[7].slice()};
const template=d.windows['packet-p7-read-output'].find(v=>v.ip===0x9C).fullBefore.ik1302;
const holds=p=>raw(p[7])===SECOND&&raw(p[10])===FIRST&&raw(p[9],0)===SECOND;
const compact=v=>({held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,writers:v.writers,
  markers:names.filter((_,j)=>v.pages[j][22]===15),P9:raw(v.pages[9]),Y:raw(v.pages[14])});
const steps=[...Array.from({length:2},()=>({reg:3,source:F,frame:'Y'})),
  {reg:10,source:ZERO,frame:'U'},{reg:4,source:THIRD,frame:'Y'},
  {reg:10,source:ZERO,frame:'U'},
  ...Array.from({length:4},()=>({reg:5,source:ZERO,frame:'Y'})),
  {reg:4,source:THIRD,frame:'Y'},
  ...(relocating?[{reg:8,source:THIRD,frame:'P9',relocateFirst:true}]:[])],path=[];
let firstLocation='P10';
for(const target of steps) {
  const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
  const ops=[...new Set(entries.map(j=>sourceRoot(current.pages,template,6,j)).filter(x=>x!==null)
    .map(root=>(target.reg+11-root+30)%15))];
  const rejected=[];let chosen=null;
  candidates:for(const operand of ops)for(const lead of [0,6,12,18,24]) {
    let holder='P10';
    const preserve=target.relocateFirst?(p,ctx)=>{
      if(ctx.ip===0xA8&&ctx.writtenWord==='P10'){if(holder!=='P10')return false;holder='A';}
      else if(ctx.ip===0xA8&&ctx.writtenWord==='aux0'){if(holder!=='A')return false;holder='aux0';}
      const actual=holder==='A'?ctx.state.r.slice(0,36).filter((_,j)=>j%3===0).reverse().map(n=>n.toString(16).toUpperCase()).join(''):raw(p[names.indexOf(holder)]);
      return actual===FIRST&&raw(p[7])===SECOND&&raw(p[9],0)===SECOND;
    }:holds;
    const next=keyCall(current,operand,lead,{preserved:preserve});
    rejected.push({operand,lead,...compact(next)});
    if(next.held&&next.ended&&next.reads[0]?.reg===target.reg&&next.reads[0]?.raw===target.source&&
      next.writers.find(([ip])=>ip===0xE7)?.[1]===target.frame){chosen={operand,lead,next,holder};break candidates;}
  }
  if(!chosen){path.push({target,failed:true,rejected});break;}
  current=chosen.next;firstLocation=chosen.holder;path.push({target,operand:chosen.operand,lead:chosen.lead,...compact(current)});
}
console.log(JSON.stringify({initialData:'ordinaryR4=1.3579246E-50 ONLY in detached model',path,
  written:raw(current.pages[9])===THIRD,P9:raw(current.pages[9]),firstLocation,
  boundary:'conditional source-selected PRIMARY writer plan; NOT native third storage/read/full K1/K2'}));
