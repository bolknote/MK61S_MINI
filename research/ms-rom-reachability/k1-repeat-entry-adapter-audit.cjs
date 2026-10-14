#!/usr/bin/env node
'use strict';
// Exact passive audit: the old closed invocation followed by a different
// entry and a clean exit. This is not two executions of the same mapping.
const assert=require('node:assert/strict');
const probe=require('./k1-repeat-entry-adapter.cjs');
const old=require('./k1-zero-rotate-stack-close-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const {mapping}=require('./k1-repeat-entry-adapter-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const surface=require('./k1-x1-retry-reader-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const word=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});
const markers=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const rotationIps='6E 5E 50 52 53 4F 24 26 28 D3 37 37 37 37 37 37 27 D4 D4 D4 D4 D4 C4 2C 3B 2B 60 37 37 37 37 27 61 3A 3A 3A 2A 39';
const ySwapIps='6E 5E 50 52 53 4F 41 43 4D 60 37 37 27 61 4E 2A 39';
const swapIps='6E 5E 50 52 53 4F 41 43 4D 60 37 37 37 37 37 37 27 61 4E 2A 39';

function publicSurface(o={}) {
  o={...probe.closedDefaults,...o};const displays=['1,','2,','3,','4,','5,','6,','7,'];
  const a=surface.record(displays,o,probe.finish);
  same(a,surface.record(displays,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,displays);same(a.result,undefined);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicKeysWaitsAndDisplayOnly:true,assumedFirstSuccessfulReaderAttempts:true};
}

function formatter(r,stage,read,late,source,zeros,small,marks) {
  const base='EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE'.split(' ').map(x=>parseInt(x,16));
  base.push(...(read.raw[0]==='9'?[0xD9]:small?[0xD0,0xF2]:[0xD0]),
    ...Array.from({length:zeros+1},()=>[0xF3,0xF7,0xF1]).flat(),
    ...Array.from({length:8-zeros},()=>[0xF4,0xF6]).flat(),0xF4,0xEA,0xEC);
  same(base.length,39+zeros+Number(small));base.push(0x40,0x41,0x42,0x46);
  while(!marks.includes(slots[(slots.indexOf(source)+base.length)%15]))base.push(0xE5);
  base.push(0xE5,0xE6,0xE8,0xE7);
  const route=r.traced.events.filter(e=>e.stage===stage&&e.command>=read.command&&e.command<=late.command);
  same(route.map(e=>[e.ip,e.slot]),base.map((ip,i)=>[ip,slots[(slots.indexOf(source)+i)%15]]),'connected formatter '+stage);
}

function operation(r,stage,endStage,spec) {
  const at=checks.boundary(r,stage),end=checks.boundary(r,endStage),es=r.traced.events.filter(e=>e.stage===stage);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),spec.gates);
  const reads=es.filter(e=>e.ip===0xEE),copies=es.filter(e=>e.ip===0xE9),requests=es.filter(e=>e.ip===0xA3),lates=es.filter(e=>e.ip===0xE7);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[[spec.source,spec.value,0xA1],[spec.lateSource,spec.lateValue,0xE3]]);
  same([copies.length,requests.length,lates.length],[1,1,1]);
  const copy=copies[0],req=requests[0],late=lates[0],allowed=new Set();
  const permit=(chip,c)=>allowed.add(chip+':'+c);
  repack.exactCopy(r,copy,spec.copy,spec.value);permit(3,copy.command);
  same(req.slot,spec.request);const expectedReq=ringAt(r,req.command);
  const rv=[parseInt(spec.value[2],16),spec.opcode%16,spec.opcode>>4];
  [28,31,34].forEach((n,i)=>{expectedReq[spec.request][n]=rv[i];});
  same(ringAt(r,req.command+1),expectedReq);
  same(r.traced.writes.filter(w=>w.command===req.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
    [28,31,34].map((n,i)=>[3,spec.request,n,rv[i]]));permit(3,req.command);
  const all=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.chip===4);
  const ack=all.filter(w=>w.ip===0x27),out=all.filter(w=>w.ip!==0x27),first=out[0].command;
  same(ack.map(w=>[w.slot,w.nibble,w.value]),spec.acks.map(n=>[n,31,15]));
  same(out.map(w=>[w.command-first,w.ip,w.slot,w.nibble]),spec.pairs.flatMap(([n],i)=>
    Array.from({length:12},(_,j)=>[i,i===spec.pairs.length-1?0x2A:(spec.pairs.length===2?0x4E:0x3A),n,1+3*j])));
  same(r.traced.writes.filter(w=>w.command>=first&&w.command<first+spec.pairs.length),out);
  const before=ringAt(r,first),after=structuredClone(before);
  for(const [dst,src] of spec.pairs)word(after,dst,raw(before[src]));
  same(ringAt(r,first+spec.pairs.length),after,'exact secondary output '+stage);
  const ips=spec.path.split(' ').map(x=>parseInt(x,16));
  const native=es.filter(e=>e.command>=req.command&&e.command<req.command+ips.length);
  same(native.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    ips.map((ip,i)=>[ip,slots[(slots.indexOf(spec.consumer)+i)%15]]));
  same(native[0].otherChips[4].r[29],0);all.forEach(w=>permit(4,w.command));
  repack.exactCopy(r,late,spec.lateTarget,spec.lateValue);permit(3,late.command);
  assert.ok(spec.lateReadAfterOutput?reads[1].command>=first+spec.pairs.length:reads[1].command<first);
  assert.ok(late.command>=first+spec.pairs.length);
  formatter(r,stage,reads[1],late,spec.lateSource,spec.zeros,spec.small??false,spec.markers);
  const expected=structuredClone(at.ring);word(expected,spec.copy,spec.value);
  [28,31,34].forEach((n,i)=>{expected[spec.request][n]=rv[i];});
  spec.acks.forEach(n=>{expected[n][31]=15;});
  for(const [dst,src] of spec.pairs)word(expected,dst,raw(at.ring[src]));
  word(expected,spec.lateTarget,spec.lateValue);same(end.ring,expected,'all 630 endpoint tetras '+stage);
  same(r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.before!==w.value&&!allowed.has(w.chip+':'+w.command)),[]);
  return {stage,earlyRead:reads[0].command,reserve:copy.command,request:req.command,
    secondaryOutput:first,lateRead:reads[1].command,lateWrite:late.command,lateTarget:spec.lateTarget};
}

function check(full) {
  const r=full.options.verifyExit?prefixView(full,'post/manual'):full;
  same(r.options.adapterPhase,2);same(r.options.adapterActions,probe.closedDefaults.adapterActions);
  same(r.options.exitActions,probe.closedDefaults.exitActions);same(r.options.lowerPush,true);
  const f=prefixView(r,'between',{verifyExit:false});
  f.traced.events=f.traced.events.map(e=>({...e,stage:e.stage.replace(/^first\//,'')}));
  const first=old.check(f);
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const [u,v,w,q,a,b]=['U','V','W','Q','P7','P8'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const end=checks.boundary(r,'done'),entry=checks.boundary(r,'adapter/0');
  const rows=repack.boundaryLosses(full);same(rows.filter(e=>e.missing.length),[]);
  same(visible(entry),[w,a,q,p,'9990FFFFFFF0']);
  const operations=[];
  const add=(stage,next,s)=>operations.push(operation(r,stage,next,s));
  add('adapter/0','second/entry/tail-0',{gates:[['control',0x9E],['control',0x9E]],
    source:'W',value:a,copy:'X1',request:'U',opcode:0x25,consumer:'T',acks:['U','U'],path:rotationIps,
    pairs:[['W','Q'],['Q','P7'],['P7','P8'],['P8','W']],lateSource:'Q',lateValue:w,lateTarget:'X',zeros:1,markers:['marker','T','U']});
  add('second/entry/tail-0','second/entry/tail-1',{gates:[['U',0x9E],['U',0x9E]],
    source:'X',value:w,copy:'V',request:'control',opcode:0x25,consumer:'marker',acks:['control','control'],path:rotationIps,
    pairs:[['X','Y'],['Y','Z'],['Z','T'],['T','X']],lateSource:'X',lateValue:w,lateTarget:'V',zeros:1,markers:['marker','Z','U']});
  add('second/entry/tail-1','exit/0',{gates:[['T',0x9E],['T',0x9E]],
    source:'X',value:q,copy:'U',request:'control',opcode:0x25,consumer:'marker',acks:['control','control'],path:rotationIps,
    pairs:[['X','Y'],['Y','Z'],['Z','T'],['T','X']],lateSource:'X',lateValue:q,lateTarget:'U',zeros:0,markers:['marker','Y']});
  add('exit/0','exit/1',{gates:[['control',0x9E],['control',0x9E]],
    source:'X',value:p,copy:'X1',request:'Z',opcode:0x14,consumer:'Y',acks:['control'],path:ySwapIps,
    pairs:[['X','V'],['Y','X']],lateSource:'X',lateValue:w,lateTarget:'X',zeros:1,markers:['marker'],lateReadAfterOutput:true});
  add('exit/1','exit/push/blind-duplicate',{gates:[['control',0x9E],['control',0x9D],['control',0x9E]],
    source:'X',value:w,copy:'X1',request:'control',opcode:0x14,consumer:'marker',acks:['control'],path:swapIps,
    pairs:[['X','Y'],['Y','X']],lateSource:'X',lateValue:p,lateTarget:'X',zeros:5,small:true,markers:['marker'],lateReadAfterOutput:true});
  const duplicate=checks.boundary(r,'exit/push/blind-duplicate'),duplicated=checks.boundary(r,'exit/push/push-marker-0');
  same(markers(duplicate),['marker']);same(visible(duplicate),[w,p,w,'14'+p[2]+w.slice(3),q]);
  const des=r.traced.events.filter(e=>e.stage==='exit/push/blind-duplicate');
  const pushes=des.filter(e=>e.ip===0xE7&&e.nextIp===0xA8).map(first=>checks.exactPush({...r,
    traced:{...r.traced,events:r.traced.events.filter(e=>e.command>=first.command)}},'exit/push/blind-duplicate',['X','Y','Z','T']));
  same(pushes.length,3);same(pushes.map(x=>x.displaced),[q,'14'+p[2]+w.slice(3),w]);
  same(visible(duplicated),[w,p,p,p,p]);
  const push=checks.exactPush(r,'exit/push/push',['T','U','V','W']);same(push.displaced,w);
  const before=ringAt(r,push.command);same(['T','U','V','W'].map(n=>raw(before[n])),[p,q,w,w]);
  const lo=duplicate.command,allowedMs=new Set([push.command+1,push.command+2,push.command+3]);
  same(r.traced.writes.filter(x=>x.command>=lo&&x.before!==x.value&&
    ((x.nibble%3===0&&x.nibble<36)||(Object.hasOwn(r.before,x.slot)&&x.nibble%3===1&&
      !(x.chip===3&&allowedMs.has(x.command)&&['U','V','W'].includes(x.slot)&&x.nibble<37)))),[]);
  const initial=r.traced.events.find(e=>e.ring),original=snapshotFromRing(initial.ring);
  same(snapshotFromRing(end.ring).words,mapping.map(i=>original.words[i]));same(markers(end),['marker']);
  const oracle=analyzeTrace({beforeEvent:initial,afterEvent:end,writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');
  if(full.options.verifyExit) {
    const done=checks.boundary(full,'done'),post=checks.boundary(full,'post/manual').command;
    same(full.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(full,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(full,'post/program').ring.X),'000000000000');
    same(raw(done.ring.X),'000050000000');same(markers(done),['marker']);
    same(snapshotFromRing(done.ring).words,snapshotFromRing(end.ring).words);
    same(full.afterProgram,full.beforeProgram);
    same(full.traced.writes.filter(w=>w.command>=post&&w.before!==w.value&&
      ((w.nibble%3===0&&w.nibble<36)||(Object.hasOwn(full.before,w.slot)&&w.nibble%3===1)||[36,37,39,40].includes(w.nibble))),[]);
  }
  return {firstCall:first.all23BackInStoredWords,boundaries:rows.length,operations,push,duplicates:pushes,
    all23BackInStoredWords:true,allExtraMarkersRemoved:true,other14OrdinaryAndLastTwoMsHeld:true,
    workingExitTested:!!full.options.verifyExit,mapping,cycles:oracle.data.cycles,
    uninterruptedDifferentSecondEntry:true,notTwoIdenticalInvocations:true,
    repeatabilityProved:false,wholeNumericDomainProved:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.closedDefaults,verifyExit:true,...JSON.parse(process.env.K1_REPEAT_ADAPTER_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(publicSurface(o)));
  const r=probe.traced(o);console.log('PASS exact adapted second entry:',JSON.stringify(check(r)));
  if(process.env.K1_REPEAT_ADAPTER_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check,operation,publicSurface};
