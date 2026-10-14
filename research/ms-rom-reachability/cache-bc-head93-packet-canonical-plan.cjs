#!/usr/bin/env node
'use strict';
// Source-directed PRIMARY-ONLY transfer planning, NOT a keyboard sweep or
// a native reachability claim. Actual available M1 zero/F ports determine
// the operand via the exact01-root; full primary ROM computes every writer.
// Each candidate uses a conditional accepted9C entry template. All5 pins,
// prefix compatibility, endpoint template and secondary/tertiary calendars
// MUST be verified on a fresh native key protocol before calling a path real.
const assert=require('node:assert/strict');
const model=require('./cache-bc-head93-primary-word-model.cjs');
const {run}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const numeric=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const ordinary=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const marks=pages=>names.filter((_,j)=>pages[j][22]===15);
const NUMBER='007012345678',ZERO='000000000000',F='0000F0000000';
function audit(data,selected=['packet-restore-aux0F','packet-idle']) {
  const fields=['r','m','st','s','s1','l','t','carry'];let checked=0;
  for(const name of selected)for(const v of data.windows[name]) {
    const result=model.step(v.fullBefore.ik1302,v.keysX[0],v.keysY[0],v.fullAfter.ik1302.m);
    for(const field of fields)assert.deepEqual(result.state[field],v.fullAfter.ik1302[field],name+'/'+v.word+'/'+field);
    assert.deepEqual(result.out,v.emitted);checked++;
  }
  console.log('PASS detached numeric interpreter',checked,'native primary words, all515 bits/output; NOT ALL5 replay.');
  return checked;
}
function pagesAt(data,record) {
  const f=record.fullBefore,t=record.tagsBefore,result=Array(15);
  const block=(chip,start=0)=>{
    const values=Array.from({length:42},(_,j)=>f[chip].m[(start+j)%f[chip].m.length]);
    const ids=Array.from({length:42},(_,j)=>t[chip][(start+j)%t[chip].length]);
    const cell=data.cells[ids[22]],name=cell.word;
    assert.ok(names.includes(name),(chip,start,cell));
    for(let j=0;j<12;j++)assert.equal(data.cells[ids[1+3*j]].field,j);
    result[names.indexOf(name)]=values;
  };
  block('ik1302');block('ik1303');block('ik1306');
  for(const chip of ['ir2a','ir2b'])for(let j=0;j<6;j++)block(chip,(f[chip].tick+42*j)%252);
  assert.ok(result.every(Boolean));return result;
}
function key(n) {return n<10?[n+2,1]:[n-3,8];}
function auditConnected(data,selected) {
  let checked=0;
  for(const name of selected) {
    const records=data.windows[name],first=records[0],pages=pagesAt(data,first);
    let a=model.clone(first.fullBefore.ik1302),here=names.indexOf(first.numericOwner[0].split(':')[1]);
    for(const v of records) {
      for(const field of ['r','m','st','s','s1','l','t','carry'])
        assert.deepEqual(a[field],v.fullBefore.ik1302[field],name+'/'+v.word+'/before/'+field);
      assert.equal(model.ip(a),v.ip);
      const result=model.step(a,v.keysX[0],v.keysY[0],pages[(here+1)%15]);
      for(const field of ['r','m','st','s','s1','l','t','carry'])
        assert.deepEqual(result.state[field],v.fullAfter.ik1302[field],name+'/'+v.word+'/after/'+field);
      assert.deepEqual(result.out,v.emitted);
      pages[here]=result.out;a=result.state;here=(here+1)%15;checked++;
    }
  }
  console.log('PASS PRIMARY-ONLY connected numeric ring',checked,'words in',selected.length,
    'separate windows; initial snapshots once/window, no state repair. NOT ALL5.');
  return checked;
}
function sourceRoot(pages,template,type=6,entryPage=9) {
  let a=model.clone(template),here=entryPage;
  a.r[29]=0;a.r[30]=0;a.r[32]=0;a.r[33]=type;a.r[35]=type;
  a.m=pages[here].slice();
  for(let i=0;i<300;i++) {
    const ip=model.ip(a);
    if(ip===1&&a.m[22]===15)return here;
    if([0xD6,0xD4,0xE7,0xA8,0xE9,0xBE].includes(ip))return null;
    a=model.step(a,...key(0),pages[(here+1)%15]).state;here=(here+1)%15;
  }
  return null;
}
function call(pages,template,reg,type=6,entryPage=9,selectedRoot=undefined,options={}) {
  const next=pages.map(p=>p.slice());let a=model.clone(template),here=entryPage;
  // Derive the actual source01 root from ordered ROM, rather than assuming
  // the first E5 startsX for every accepted9C page/calendar. Verify D6/D4's
  // physical ordinary owner below so a numeric0/F alias cannot hide a bug.
  const root=selectedRoot===undefined?sourceRoot(pages,template,type,entryPage):selectedRoot;
  if(root===null)return null;
  const operand=(reg+11-root+30)%15;
  a.r[29]=operand;a.r[30]=operand;a.r[32]=operand;a.r[33]=type;a.r[35]=type;
  a.m=next[here].slice();const pins=key(operand),route=[],writers=[];let source=null,sourceReg=null;
  for(let i=0;i<500;i++) {
    const ip=model.ip(a);
    if(ip===0xBE)return {pages:next,operand,reg,root,type,source,sourceReg,writers,route};
    if(ip===0xD6){
      source=ordinary(a.m);sourceReg=(here-3+15)%15;
      if(sourceReg!==reg||!(options.allowedSources||[ZERO,F]).includes(source))return null;
    }
    if(ip===0xD4&&(here-3+15)%15!==reg)return null;
    if([0xD4,0xE7,0xA8,0xE9].includes(ip))writers.push([ip,names[here]]);
    route.push([ip,names[here]]);
    const result=model.step(a,...pins,next[(here+1)%15]);
    next[here]=result.out;a=result.state;here=(here+1)%15;
    if(options.preserveP10!==false&&numeric(next[10])!==NUMBER)return null;
    if(options.preserved&&!options.preserved(next))return null;
  }
  return null;
}
function runPlan() {
  const data=run({proof:true,phase:'yc1'});audit(data);
  const records=data.windows['packet-restore-aux0F'],first=records[0];
  const original=pagesAt(data,first),template=first.fullBefore.ik1302;
  assert.equal(numeric(original[10]),NUMBER);
  const simulated=call(original,template,3);
  assert.ok(simulated);assert.equal(simulated.operand,6);
  assert.deepEqual(simulated.route,records.map(v=>[v.ip,v.numericOwner[0].split(':')[1]]).slice(0,-1));
  assert.deepEqual(marks(simulated.pages),['P8','aux0']);
  for(let j=0;j<15;j++)assert.equal(numeric(simulated.pages[j]),data.exitStages.at(-1).words[
    ['P7','P8','P9','P10'].includes(names[j])?'Ms:'+names[j]:names[j]]);
  console.log('PASS PRIMARY-ONLY connected139-word seed route/end numeric words agree with native; other chips/template NOT yet generalized.');
  const signature=pages=>pages.map(p=>numeric(p)+ordinary(p)).join('/');
  const queue=[{pages:simulated.pages,path:[{type:6,operand:6,reg:3,writers:simulated.writers}]}];
  const seen=new Set([signature(simulated.pages)]),limit=Number(process.argv.find(a=>a.startsWith('--limit='))?.split('=')[1]||3000);
  let intermediate=false;
  for(let i=0;i<queue.length&&i<limit;i++) {
    const item=queue[i];
    if(!intermediate&&item.pages[11][22]===15&&item.pages[8][22]!==15) {
      intermediate=true;console.log('CONDITIONAL INTERMEDIATE',JSON.stringify({path:item.path,markers:marks(item.pages),inspected:i+1}));
    }
    if(marks(item.pages).join(',')==='aux0') {
      console.log(JSON.stringify({conditionalPlan:item.path,markers:marks(item.pages),
        inspected:i+1,queued:queue.length,
        numeric: Object.fromEntries(names.map((n,j)=>[n,numeric(item.pages[j])])),
        boundary:'PRIMARY conditional plan only; native prefix/ALL5/actions not yet verified'}));return;
    }
    if(item.path.length>=18)continue;
    const ports=item.pages.map((p,j)=>({p:ordinary(p),j})).filter(o=>[ZERO,F].includes(o.p))
      .map(o=>(o.j-3+15)%15); // Z->RC, T->RD, ...
    const actions=ports.map(reg=>({type:6,reg}));
    // Deliberate interface adaptation only: R9/F skipsX to reachY; R8/zero
    // prevents the known preceding-F effect when that R9 port is read.
    const first=Array.from({length:15},(_,j)=>(13+j)%15).find(j=>item.pages[j][22]===15);
    if(first!==undefined&&[ZERO,F].includes(numeric(item.pages[(first+3)%15])))
      for(const reg of [8,9])actions.push({type:4,reg});
    for(const {type,reg} of actions) {
      const result=call(item.pages,template,reg,type);
      if(result) {
        const sig=signature(result.pages);if(seen.has(sig))continue;seen.add(sig);
        queue.push({pages:result.pages,path:[...item.path,{type,operand:result.operand,reg,
          root:result.root,source:result.source,writers:result.writers}]});
      }
    }
  }
  console.log(JSON.stringify({conditionalPlan:null,queued:seen.size,limit,
    boundary:'bounded primary-only transfer exploration, NOT global impossibility or keyboard sweep'}));
}
if(require.main===module)runPlan();
module.exports={audit,auditConnected,pagesAt,call,sourceRoot};
