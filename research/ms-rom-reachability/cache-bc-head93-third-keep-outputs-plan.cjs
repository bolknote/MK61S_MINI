#!/usr/bin/env node
'use strict';
// Return to ordinary geometry but keep BOTH genuine readout values in
// realR6/R7. They are explicit transient holders for a later P9 write.
// Not normal work without reserves, and not a native third-word protocol.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=(p,l=1)=>p.filter((_,j)=>j%3===l).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357',ZERO='000000000000',F='0000F0000000';
function run(file) {
  const d=JSON.parse(fs.readFileSync(file,'utf8')),entry=d.endpoints['packet-p7-first-output'];
  const template=d.windows['packet-p7-first-output'].find(v=>v.ip===0x9C).fullBefore.ik1302;
  let current={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const preserved=p=>raw(p[7])===SECOND&&raw(p[10])===FIRST&&raw(p[9],0)===SECOND&&raw(p[10],0)===FIRST;
  assert.ok(preserved(current.pages));
  const path=[],steps=[{kind:'cx'},{reg:3,source:F,frame:'aux0'},
    {kind:'store',reg:5,source:F},{reg:5,source:F,frame:'Y'},{reg:8,source:F,frame:'X1'},
    ...Array.from({length:3},()=>({reg:7,source:FIRST,frame:'X1'})),
    {kind:'cx',clear:'P8'},{header:'aux1'},{reg:8,source:F,frame:'X1'},
    ...Array.from({length:4},()=>({reg:4,source:ZERO,frame:'Y'})),{kind:'store',reg:5,source:ZERO}];
  for(const target of steps) {
    const kind=target.kind||'rcl';
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const ops=target.header?[8,4,0]:kind==='cx'?[0]:[...new Set(entries.map(j=>sourceRoot(current.pages,template,kind==='store'?4:6,j))
      .filter(x=>x!==null).map(root=>(target.reg+11-root+30)%15))];
    const rejected=[];let chosen=null;
    candidates:for(const operand of ops)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{kind,preserved});
      rejected.push({operand,lead,held:next.held,ended:next.ended,reads:next.reads,writers:next.writers,
        markers:names.filter((_,j)=>next.pages[j][22]===15)});
      if(!next.held)continue;
      if(target.header){if(!next.writers.some(([ip,n])=>ip===0xA3&&n===target.header))continue;}
      else{
        if(!next.ended)continue;
        if(target.clear&&next.pages[names.indexOf(target.clear)][22]===15)continue;
        if(kind==='rcl'&&(next.reads[0]?.reg!==target.reg||next.reads[0]?.raw!==target.source||next.writers.find(([ip])=>ip===0xE7)?.[1]!==target.frame))continue;
        if(kind==='store'&&(raw(next.pages[(target.reg+3)%15],0)!==target.source||next.writers.find(([ip])=>ip===0xD4)?.[1]!==names[(target.reg+3)%15]))continue;
      }
      chosen={operand,lead,next};break candidates;
    }
    if(!chosen){path.push({target,failed:true,rejected});break;}
    current=chosen.next;path.push({target,operand:chosen.operand,lead:chosen.lead,
      writers:current.writers,markers:names.filter((_,j)=>current.pages[j][22]===15)});
  }
  return {path,canonical:names.filter((_,j)=>current.pages[j][22]===15).join(',')==='aux0',
    holders:{R6:raw(current.pages[9],0),R7:raw(current.pages[10],0),P7:raw(current.pages[7]),P10:raw(current.pages[10])},
    boundary:'PRIMARY output-retaining return; transient reserves explicit, not native third storage/full K1/K2'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run};
