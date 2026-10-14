#!/usr/bin/env node
'use strict';
// Detached PRIMARY plan from a genuine public-key third-write endpoint.
// No initial-data edits. R7/R6/R4 are explicit, observed transient holders.
// Two frame pushes may restore FIRST to P10 while rewriting THIRD to P9.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=(p,l=1)=>Array.from({length:12},(_,j)=>p[l+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',THIRD='950013579246';
const compact=v=>({held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,writers:v.writers,
  markers:names.filter((_,j)=>v.pages[j][22]===15),words:Object.fromEntries(names.map((n,j)=>[n,raw(v.pages[j])]))});
function run(file){
  const d=JSON.parse(fs.readFileSync(file,'utf8')),entry=d.endpoints['packet-third-write-P9'];
  assert.equal(d.schema,'mk61-third-write-passive-v1');
  const template=d.windows['packet-third-write-P9'].find(v=>v.ip===0x9C).fullBefore.ik1302;
  const inlet={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const holds=p=>raw(p[7])===SECOND&&raw(p[10],0)===FIRST&&raw(p[9],0)===SECOND&&raw(p[7],0)===THIRD;
  assert.ok(holds(inlet.pages));
  const candidates=(cur,reg,source,frame)=>{
    const entries=names.map((_,j)=>j).filter(j=>cur.pages[j][31]===15?cur.pages[j][34]>=1:cur.pages[j][34]>=7);
    const ops=[...new Set(entries.map(j=>sourceRoot(cur.pages,template,6,j)).filter(x=>x!==null)
      .map(root=>(reg+11-root+30)%15))];
    const attempts=[],success=[];
    for(const operand of ops)for(const lead of [0,6,12,18,24]){
      const next=keyCall(cur,operand,lead,{preserved:holds});
      const match=next.held&&next.ended&&next.reads[0]?.reg===reg&&next.reads[0]?.raw===source&&
        next.writers.find(([ip])=>ip===0xE7)?.[1]===frame;
      attempts.push({operand,lead,match,...compact(next)});
      if(match)success.push({operand,lead,next});
    }
    return{attempts,success};
  };
  const first=candidates(inlet,7,FIRST,'P9'),paths=[],adapters=[];let relocation=null;
  // The native endpoint has an extra aux1/F. A request in X is an observed
  // non-payload header adaptation, not an injected control value.
  for(const lead of [0,6,12,18,24]){
    const next=keyCall(inlet,12,lead,{preserved:holds});
    if(next.held&&next.writers.some(([ip,n])=>ip===0xA3&&n==='X')){
      const after=candidates(next,7,FIRST,'P9');
      adapters.push({operand:12,lead,...compact(next),attempts:after.attempts});
      first.success.push(...after.success.map(a=>({...a,adapter:{operand:12,lead}})));
    }
  }
  const recovered=keyCall(inlet,0,0,{kind:'lastx',preserved:holds});
  if(recovered.held&&recovered.ended&&recovered.pages[12][22]!==15){
    const after=candidates(recovered,7,FIRST,'P9');
    adapters.push({kind:'lastx',operand:0,lead:0,...compact(recovered),attempts:after.attempts});
    first.success.push(...after.success.map(a=>({...a,adapter:{kind:'lastx',operand:0,lead:0}})));
    const moved=after.success.find(a=>raw(a.next.pages[7])===SECOND&&raw(a.next.pages[9])===FIRST&&raw(a.next.pages[10])===THIRD);
    if(moved)relocation={steps:[{kind:'lastx',operand:0,lead:0},{kind:'rcl',reg:7,operand:moved.operand,lead:moved.lead}],
      ...compact(moved.next),boundary:'three physical bank words, not the original P9=THIRD/P10=FIRST layout or a canonical work cycle'};
  }
  for(const a of first.success){
    assert.equal(raw(a.next.pages[9]),FIRST);
    const second=candidates(a.next,4,THIRD,'P9');
    for(const b of second.success)paths.push({adapter:a.adapter||null,steps:[{reg:7,operand:a.operand,lead:a.lead,...compact(a.next)},
      {reg:4,operand:b.operand,lead:b.lead,...compact(b.next)}],
      restored:raw(b.next.pages[9])===THIRD&&raw(b.next.pages[10])===FIRST&&raw(b.next.pages[7])===SECOND,
      current:b.next});
    if(paths.some(p=>p.restored))break;
  }
  return{file,firstAttempts:first.attempts,adapters,paths,relocation,
    boundary:'PRIMARY-only continuation from native evidence; transient sources explicit, not native restoration/full K1/K2'};
}
if(require.main===module){const v=run(process.argv[2]);console.log(JSON.stringify({...v,paths:v.paths.map(({current,...p})=>p)}));}
module.exports={run,names,raw,compact,FIRST,SECOND,THIRD};
