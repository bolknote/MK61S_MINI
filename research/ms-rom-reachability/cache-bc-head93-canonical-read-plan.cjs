#!/usr/bin/env node
'use strict';
// ROM transfer planning from the genuinely restored stock endpoint.
// Conditional primary-only entries, NOT keyboard reachability or ALL5 proof.
// A candidate must be checked by fixed keys on a fresh full stock emulator.
const assert=require('node:assert/strict');
const {run}=require('./cache-bc-head93-canonical-number-native.cjs');
const model=require('./cache-bc-head93-primary-word-model.cjs');
const {pagesAt,call,sourceRoot,auditConnected}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const numeric=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const ordinary=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const marks=pages=>names.filter((_,j)=>pages[j][22]===15);
const ZERO='000000000000',F='0000F0000000',NUMBER='007012345678';

function runPlan() {
  const data=run({proof:true});
  auditConnected(data,['packet-clean-read2','packet-clean-backup-zero','packet-idle']);
  const template=data.windows['packet-clean-read2'][0].fullBefore.ik1302;
  const original=pagesAt(data,data.windows['packet-idle'][0]);
  const entryPage=12;
  assert.equal(model.ip(template),0x9C);
  assert.equal(numeric(original[10]),NUMBER);assert.deepEqual(marks(original),['aux0']);
  assert.ok(!original.some(p=>ordinary(p)===NUMBER));
  const sig=pages=>pages.map(p=>numeric(p)+ordinary(p)).join('/');
  const queue=[{pages:original,path:[]}],seen=new Set([sig(original)]);
  const limit=Number(process.argv.find(a=>a.startsWith('--limit='))?.split('=')[1]||3000);
  for(let i=0;i<queue.length&&i<limit;i++) {
    const item=queue[i];
    const first=Array.from({length:15},(_,j)=>(13+j)%15).find(j=>item.pages[j][22]===15);
    if(first===8) {
      console.log(JSON.stringify({conditionalPlan:item.path,markers:marks(item.pages),
        firstFromX:names[first],inspected:i+1,queued:queue.length,
        ordinary:item.pages.map(ordinary),numeric:Object.fromEntries(names.map((n,j)=>[n,numeric(item.pages[j])])),
        boundary:'accepted primary-only templates; native entry/control/source/read/exit NOT yet proved'}));
      return;
    }
    if(item.path.length>=14)continue;
    const ports=item.pages.map((p,j)=>({p:ordinary(p),j})).filter(o=>[ZERO,F].includes(o.p))
      .map(o=>(o.j-3+15)%15);
    const roots=Object.fromEntries([4,6].map(type=>[type,sourceRoot(item.pages,template,type,entryPage)]));
    const actions=ports.map(reg=>({type:6,reg}));
    // STORE is an interface port constructor, not arbitrary payload writes.
    // Only the actual realP5 port used by the proven clean return is offered.
    if(first!==undefined&&[ZERO,F].includes(numeric(item.pages[(first+3)%15])))
      actions.push({type:4,reg:5});
    for(const {type,reg} of actions) {
      const result=call(item.pages,template,reg,type,entryPage,roots[type]);
      if(!result)continue;
      const signature=sig(result.pages);if(seen.has(signature))continue;seen.add(signature);
      queue.push({pages:result.pages,path:[...item.path,{type,operand:result.operand,reg,
        root:result.root,source:result.source,sourceReg:result.sourceReg,
        markers:marks(result.pages),writers:result.writers}]});
    }
  }
  console.log(JSON.stringify({conditionalPlan:null,inspected:Math.min(limit,queue.length),
    queued:queue.length,boundary:'bounded primary-only marker/port transfers; NOT impossibility or native key sweep'}));
}
if(require.main===module)runPlan();
module.exports={runPlan};
