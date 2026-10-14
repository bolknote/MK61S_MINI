#!/usr/bin/env node
'use strict';
// Conditional ROM transfers to a P7-only writer root. Available physical
// M1 zero/F ports, real D6/D4 owners and a protected realR6 backup determine
// actions. Not a native keyboard sweep or a successful second stored word.
const assert=require('node:assert/strict');
const model=require('./cache-bc-head93-primary-word-model.cjs');
const {run}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const {pagesAt,call,sourceRoot,auditConnected}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const numeric=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const ordinary=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const marks=pages=>names.filter((_,j)=>pages[j][22]===15);
const F='0000F0000000',ZERO='000000000000',FIRST='007012345678';
const SECOND='007024681357';
const sig=p=>p.map(w=>numeric(w)+ordinary(w)).join('/');
function signPrefix(pages,template,entryPage) {
  let a=model.clone(template),here=entryPage;const next=pages.map(p=>p.slice());
  a.m=next[here].slice();let sourcePage=null;
  for(let i=0;i<300;i++) {
    const ip=model.ip(a);
    if(ip===0xEE&&sourcePage===null)sourcePage=here;
    if(ip===0xE9)return {sourcePage,writerPage:here,source:numeric(next[sourcePage]),
      working:Array.from({length:12},(_,j)=>a.r[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('')};
    if([0x9D,0xBE].includes(ip))return null;
    const result=model.step(a,7,1,next[(here+1)%15]);next[here]=result.out;
    a=result.state;here=(here+1)%15;
  }
  return null;
}
function plan() {
  const withData=process.argv.includes('--with-data');
  const data=run({proof:true,phase:'yku',secondPhase:withData?'p9-source-write':'seed'});
  const rec=data.windows[withData?'packet-second-open1':'packet-second-probe-zero'][0];
  const inlet=withData?data.exitStages.find(s=>s.name==='packet-second-source-flush4'):data.exitStages.at(-1);
  assert.deepEqual(inlet.markers,['aux0']);
  assert.equal(inlet.registers[6],FIRST);assert.equal(inlet.words['Ms:P10'],FIRST);
  auditConnected(data,withData?['packet-second-source-store','packet-second-open1','packet-second-open4','packet-second-open5']:
    ['packet-second-backup-first','packet-second-probe-zero','packet-idle']);
  const original=pagesAt(data,withData?rec:data.windows['packet-idle'][0]);
  const template=rec.fullBefore.ik1302;
  const entryPage=names.indexOf(rec.numericOwner[0].split(':')[1]);
  const signTemplate=data.windows['packet-sign-repeat'][0].fullBefore.ik1302;
  const test=call(pagesAt(data,rec),template,withData?12:0,6,entryPage);
  assert.ok(test);assert.equal(test.sourceReg,withData?12:0);
  assert.deepEqual(test.route,data.windows[withData?'packet-second-open1':'packet-second-probe-zero'].slice(0,-1)
    .map(v=>[v.ip,v.numericOwner[0].split(':')[1]]));
  console.log('PASS native temporaryR6 backup/aux0-only seed and exact primary conditional RCL0 interface; NOT a second stored number.');
  const queue=[{pages:original,path:[]}],seen=new Set([sig(original)]);
  const limit=Number(process.argv.find(x=>x.startsWith('--limit='))?.split('=')[1]||5000);
  for(let i=0;i<queue.length&&i<limit;i++) {
    const item=queue[i];
    const entries=Array.from({length:15},(_,j)=>j).filter(j=>
      item.pages[j][31]===15?item.pages[j][34]>=1:item.pages[j][34]>=7);
    let writer=null;
    for(const entry of entries) {
      const result=signPrefix(item.pages,signTemplate,entry);
      if(result&&result.writerPage===9&&item.pages[result.sourcePage][22]!==15) {
        if(withData) {
          if(result.working===SECOND){writer={entryPage:entry,sourcePage:result.sourcePage,
            sourceWord:names[result.sourcePage],writerWord:'P9',actualStagedWord:SECOND};break;}
          continue;
        }
        const hypothetical=item.pages.map(p=>p.slice()),number='007024681357';
        for(let j=0;j<12;j++)hypothetical[result.sourcePage][1+3*j]=parseInt(number[11-j],16);
        const checked=signPrefix(hypothetical,signTemplate,entry);
        if(checked&&checked.writerPage===9&&checked.source===number) {
          writer={entryPage:entry,sourcePage:result.sourcePage,sourceWord:names[result.sourcePage],
            writerWord:'P9',hypotheticalEnteredWord:number};break;
        }
      }
    }
    if(writer||marks(item.pages).join(',')==='P7') {
      console.log(JSON.stringify({conditionalPlan:item.path,markers:marks(item.pages),
        writer,inspected:i+1,queued:queue.length,numeric:Object.fromEntries(names.map((n,j)=>[n,numeric(item.pages[j])])),
        M1:Object.fromEntries(item.pages.map((p,j)=>[(j-3+15)%15,ordinary(p)])),
        boundary:'accepted primary-only template; native entry compatibility, second write, P9 preservation/read and ALL5 still unproved'}));return;
    }
    if(item.path.length>=18)continue;
    const readPorts=item.pages.map((p,j)=>({p:ordinary(p),reg:(j-3+15)%15}))
      .filter(x=>(withData?[ZERO,F,FIRST,SECOND]:[ZERO,F]).includes(x.p)).map(x=>x.reg);
    const actions=[];
    // F-port adaptation is the same mechanism as the proven transientP5/F.
    // Exclude the numerical backupR6; it may NOT be synthesized or changed.
    for(const entry of entries) {
      const root6=sourceRoot(item.pages,template,6,entry),root4=sourceRoot(item.pages,template,4,entry);
      for(const reg of readPorts)actions.push({reg,type:6,root:root6,entry});
      for(const reg of [0,2,4,5,8,9,14])if(reg!==6&&(!withData||reg!==7))actions.push({reg,type:4,root:root4,entry});
    }
    for(const {reg,type,root,entry} of actions) {
      const result=call(item.pages,template,reg,type,entry,root,{
        preserveP10:false,allowedSources:withData?[ZERO,F,FIRST,SECOND]:[ZERO,F],
        preserved:p=>ordinary(p[9])===FIRST&&(!withData||ordinary(p[10])===SECOND)});
      if(!result||!result.pages.every(p=>[ZERO,F,FIRST,SECOND].includes(ordinary(p))))continue;
      const id=sig(result.pages);if(seen.has(id))continue;seen.add(id);
      queue.push({pages:result.pages,path:[...item.path,{type,reg,operand:result.operand,
        source:result.source,root:result.root,entryPage:entry,markers:marks(result.pages),writers:result.writers}]});
    }
  }
  console.log(JSON.stringify({conditionalPlan:null,inspected:Math.min(limit,queue.length),queued:queue.length,
    boundary:'bounded zero/F transfer planning, not global impossibility or native key reachability'}));
}
if(require.main===module)plan();
module.exports={plan};
