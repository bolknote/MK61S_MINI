#!/usr/bin/env node
'use strict';
// Device-derived alternative: F at U makes the late formatter stop BEFORE
// W, avoiding P8. A following zero frame carries oldU->V and oldW->Q.
// PRIMARY only; public full-key schedule, no state repair/device import.
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {pagesAt,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const raw=p=>p.filter((_,j)=>j%3===1).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const marks=p=>names.filter((_,j)=>p[j][22]===15);
const FIRST='007012345678',SECOND='007024681357',F='0000F0000000',ZERO='000000000000';
const holds=p=>raw(p[8])===SECOND&&raw(p[10])===FIRST;
function summary(v){return {held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,
  writers:v.writers,markers:marks(v.pages),P7:raw(v.pages[7]),P8:raw(v.pages[8]),P10:raw(v.pages[10])};}
function run(file) {
  const data=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(data.schema,'mk61-two-word-reopen-passive-v1');
  assert.ok(data.metadata.onlyPublicKeys&&data.metadata.ALL5mirror);
  for(const [p,wanted] of Object.entries(data.metadata.frozenSha256))
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex'),wanted);
  const entry=data.endpoints['packet-reopen-control-front3'];
  const template=data.windows['packet-reopen-control-front3'].find(v=>v.ip===0x9C&&
    (v.fullBefore.ik1302.m[31]===15?v.fullBefore.ik1302.m[34]>=1:v.fullBefore.ik1302.m[34]>=7)).fullBefore.ik1302;
  let current={state:entry.fullBefore.ik1302,pages:pagesAt(data,entry),
    here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const path=[];
  const targets=[...Array.from({length:3},()=>({reg:3,frame:'Y',source:F})),
    {kind:'cx',clear:'Y'},{reg:8,frame:'U',source:F},{reg:10,frame:'U',source:ZERO},
    ...(process.argv.includes('--clear-v')?[{kind:'cx',clear:'V'}]:[])];
  for(const target of targets) {
    const kind=target.kind||'rcl';
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const ops=kind==='cx'?[0]:[...new Set(entries.map(j=>sourceRoot(current.pages,template,6,j))
      .filter(x=>x!==null).map(root=>(target.reg+11-root+30)%15))];
    let chosen=null;const rejected=[];
    candidates:for(const operand of ops)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead,{kind,preserved:holds});
      rejected.push({operand,lead,...summary(next)});
      if(!next.held||!next.ended)continue;
      if(target.clear&&next.pages[names.indexOf(target.clear)][22]===15)continue;
      if(kind==='rcl'&&(next.reads[0]?.reg!==target.reg||next.reads[0]?.raw!==target.source||
        next.writers.find(([ip])=>ip===0xE7)?.[1]!==target.frame))continue;
      chosen={operand,lead,next};break candidates;
    }
    if(!chosen){path.push({target,failed:true,ops,rejected});break;}
    current=chosen.next;path.push({target,operand:chosen.operand,lead:chosen.lead,...summary(current)});
  }
  const readers=[0,6,12,18,24].map(lead=>({lead,...summary(keyCall(current,0,lead,
    {kind:'lastx',preserved:holds}))}));
  console.log(JSON.stringify({path,frontier:marks(current.pages),readers,
    boundary:'F-source bypass PRIMARY hypothesis from genuine V/aux0; NOT native Q/reader/repeat'}));
}
if(require.main===module)run(process.argv[2]);
module.exports={run};
