#!/usr/bin/env node
'use strict';
// Source-directed removal of aux0/F from the genuine pre-SWAP V/aux0.
// Detached PRIMARY key schedule only. Does not import anything into stock.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-second-reopen-swap-native.cjs');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=(p,lane=1)=>p.filter((_,j)=>j%3===lane).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const marks=p=>names.filter((_,j)=>p[j][22]===15);
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000';
const holds=p=>raw(p[8])===SECOND&&raw(p[10])===FIRST;
function compact(v){return {held:v.held,ended:v.ended,decoded:v.firstDecode?.owner,
  reads:v.reads,numericReads:v.numericReads,writers:v.writers,markers:marks(v.pages),
  P7:raw(v.pages[7]),P8:raw(v.pages[8]),P10:raw(v.pages[10])};}
function run() {
  const data=prepare({proof:true}),endpoint=data.nativeEndpoints['packet-reopen-control-front3'];
  const template=data.windows['packet-reopen-control-front3'].find(v=>v.ip===0x9C&&
    (v.fullBefore.ik1302.m[31]===15?v.fullBefore.ik1302.m[34]>=1:v.fullBefore.ik1302.m[34]>=7)).fullBefore.ik1302;
  let current={state:endpoint.fullBefore.ik1302,pages:pagesAt(data,endpoint),
    here:names.indexOf(endpoint.numericOwner[0].split(':')[1])};
  assert.deepEqual(marks(current.pages),['V','aux0']);assert.ok(holds(current.pages));
  const path=[];
  for(let i=0;i<4;i++) {
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const roots=entries.map(j=>({entry:names[j],root:sourceRoot(current.pages,template,6,j)}));
    const operands=[...new Set(roots.filter(v=>v.root!==null).map(v=>(2+11-v.root+30)%15))];
    const rejected=[];let chosen=null;
    candidates:for(const operand of operands)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{preserved:holds});
      rejected.push({operand,lead,...compact(next)});
      if(next.held&&next.ended&&next.reads[0]?.reg===2&&next.reads[0]?.raw===ZERO&&
        next.writers.find(([ip])=>ip===0xE7)?.[1]==='aux0') {
        chosen={operand,lead,next};break candidates;
      }
    }
    if(!chosen){path.push({target:'R2/0 -> aux0 frame',roots,operands,failed:true,rejected});break;}
    current=chosen.next;path.push({operand:chosen.operand,lead:chosen.lead,...compact(current)});
  }
  const single=marks(current.pages).join(',')==='V';
  console.log(JSON.stringify({path,singleV:single,frontier:marks(current.pages),
    boundary:'conditional PRIMARY whole-key aux0-clear plan; NOT native SWAP output/repeat/full K1/K2'}));
}
if(require.main===module)run();
module.exports={run};
