#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-z-reserve-restored.cjs');
const reserve=require('./k1-y-t-rotate-reserve-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const lower=e=>['U','V','W','Q'].map(n=>raw(e.ring[n]));
const markers=ring=>Object.keys(ring).filter(n=>ring[n][22]===15).sort();
const setWord=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});
const m='9990FFFFFFF0',zero='000000000000';

function surface(o={}) {
  const ds=['1,','2,','3,','4,','5,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}

function unmark(r,endStage='z-exit/v-to-x-0') {
  const prefix=reserve.check(r,'rotate/tail-0');
  const at=checks.boundary(r,'rotate/tail-0'),end=checks.boundary(r,endStage);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  same(visible(at),[q,u,'25'+q.slice(2),m,v]);same(lower(at),[v,u,q,p]);
  const h='25'+u[2]+v.slice(3);
  same(visible(end),[u,u,h,u,v]);same(lower(end),[u,u,q,p]);same(markers(end.ring),['marker']);
  const es=r.traced.events.filter(e=>e.stage==='rotate/tail-0');
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]),'complete secondary observations');
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E],['control',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['V',u,0xA1],['X',u,0xE3]]);
  const saves=es.filter(e=>e.ip===0xE9);same(saves.length,1);repack.exactCopy(r,saves[0],'X1',u);
  const reqs=es.filter(e=>e.ip===0xA3);same(reqs.length,1);const req=reqs[0];same(req.slot,'T');
  const afterReq=ringAt(r,req.command);setWord(afterReq,'T',h);
  same(ringAt(r,req.command+1),afterReq,'exact pending request among all 630 tetras');
  same(r.traced.writes.filter(w=>w.command===req.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
    [28,31,34].map((n,i)=>[3,'T',n,[parseInt(u[2],16),5,2][i]]));

  const writes=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
  const secondary=writes.filter(w=>w.chip===4),acks=secondary.filter(w=>w.ip===0x27);
  same(acks.map(w=>[w.slot,w.nibble]),Array.from({length:4},()=>['control',31]));
  assert.ok(acks.every(w=>w.before===w.value));
  const outputs=secondary.filter(w=>w.ip!==0x27);same(outputs.length,96);
  const first=outputs[0].command,second=outputs[48].command;
  const late=es.filter(e=>e.ip===0xE7);same(late.length,1);same(late[0].slot,'U');
  same(late[0].command,second+3,'primary U overwrite and secondary T output share one command');
  same(raw(late[0].r,0),u,'formatter retained all 12 tetras of old X');
  same(reads[1].command,first-1,'formatter reads old X before the first output');
  const scan=es.find(e=>e.command===second);
  same([scan.ip,scan.slot,scan.m[22],scan.nextIp],[0xE5,'Y',15,0xE6],
    'formatter selects Y one command before the second pass removes it');
  for(const [index,cmd,pairs] of [[0,first,[['X','W'],['Y','Z'],['Z','T'],['T','V']]],
    [1,second,[['X','V'],['Y','Z'],['Z','T'],['T','U']]]]) {
    same(outputs.slice(index*48,(index+1)*48).map(w=>[w.command-cmd,w.ip,w.slot,w.nibble]),
      ['X','Y','Z','T'].flatMap((n,i)=>Array.from({length:12},(_,j)=>[i,i===3?0x2A:0x3A,n,1+3*j])));
    const before=ringAt(r,cmd),expected=structuredClone(before);
    for(const [dst,src] of pairs)setWord(expected,dst,raw(before[src]));
    if(index)setWord(expected,'U',u);
    same(ringAt(r,cmd+4),expected,'exact secondary output '+index+' and its concurrent primary writer');
  }
  const firstEnd=ringAt(r,first+4);
  same(['X','Y','Z','T'].map(n=>raw(firstEnd[n])),[q,m,h,u]);
  same(markers(firstEnd),['Y','marker']);
  const routes=[
    [first-28,5,[0x6E,0x5E,0x50,0x52,0x53,0x4F,0x24,0x26,0x28,0xD3,0x37,0x27,
      0xD4,0xD4,0xD4,0xD4,0xD4,0xC4,0x2C,0x3B,0x2B,0x60,0x37,0x37,0x37,0x37,0x27,0x61,
      0x3A,0x3A,0x3A,0x2A,0x39]],
    [second-29,4,[0x6E,0x5E,0x50,0x52,0x53,0x4F,0x24,0x26,0x28,0xD3,0x37,0x37,0x27,
      0xD4,0xD4,0xD4,0xD4,0xD4,0xC4,0x2C,0x3B,0x2B,0x60,0x37,0x37,0x37,0x37,0x27,0x61,
      0x3A,0x3A,0x3A,0x2A,0x39]],
  ];
  for(const [start,slot,path] of routes) {
    const rows=es.filter(e=>e.command>=start&&e.command<start+path.length);
    same(rows.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),path.map((ip,i)=>[ip,slots[(slot+i)%15]]));
    const a=rows[0].otherChips[4];same([a.r[29],a.st[36],a.st[39],a.st[37],a.st[40]],[0,10,3,10,3]);
  }
  const allowed=new Set([saves[0].command,req.command,...outputs.map(w=>w.command)]);
  same(writes.filter(w=>w.before!==w.value&&!allowed.has(w.command)),[],'no undeclared changes during unmark');
  const primary=writes.filter(w=>w.chip===3&&w.command===late[0].command);
  same(primary.map(w=>[w.slot,w.nibble]),Array.from({length:12},(_,j)=>['U',1+3*j]));
  same(primary.map(w=>w.value),[...u].reverse().map(x=>parseInt(x,16)));
  const expected=structuredClone(at.ring);
  for(const [n,value] of Object.entries({X1:u,X:u,Y:h,Z:u,T:v,U:u}))setWord(expected,n,value);
  same(end.ring,expected,'complete unmark endpoint, all 630 tetras');
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  same(original.filter(x=>!snapshotFromRing(end.ring).words.includes(x)),[v]);
  same(['X1','X','Y','Z','T'].filter(n=>raw(end.ring[n])===v),['T']);
  return {prefix,request:req.command,firstOutput:first,secondOutput:second,
    lateUOverwrite:late[0].command,extraMarkersRemoved:true,vOnlyInT:true};
}

function check(r) {
  assert.ok(!r.options.stopAfterUnmark);
  const clearing=unmark(r);
  const at=s=>checks.boundary(r,s),end=at(r.options.verifyExit?'post/manual':'done');
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const post=r.options.verifyExit?at('post/program').command:Infinity;
  checks.protectedFields({...r,traced:{...r.traced,
    events:r.traced.events.filter(e=>e.command<post),writes:r.traced.writes.filter(w=>w.command<post)}},
    [0],['U','V','W','Q']);
  assert.ok(r.traced.writes.filter(w=>w.command<post&&w.slot==='marker'&&w.nibble%3===1&&w.nibble<37)
    .every(w=>w.before===w.value),'true marker held, including temporary writes');
  same(raw(at('z-exit/read-q/attempt-0/read-prep-0').ring.X),v);
  const ready=at('z-exit/save-q');same(visible(ready).slice(1),[q,zero,v,w]);same(lower(ready),[u,u,q,p]);
  const saved=at('z-exit/first/push-marker-0');same(raw(saved.ring.U,0),q);
  same(visible(saved).slice(1),[q,zero,v,w]);
  const first=checks.exactPush(r,'z-exit/first/push',['T','U','V','W']);same(first.displaced,q);
  const middle=at('z-exit/v-to-t-0');same(lower(middle),[w,u,u,p]);
  same(visible(middle).slice(1),[zero,v,r.beforeRegisters[9],r.beforeRegisters[9]]);
  const secondAt=at('z-exit/second/push-marker-0');same(raw(secondAt.ring.T),v);
  const second=checks.exactPush(r,'z-exit/second/push',['T','U','V','W']);same(second.displaced,u);
  same(lower(end),[v,w,u,p]);same(markers(end.ring),['marker']);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:q));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+v,V:r.before.V.slice(0,2)+w,
    W:r.before.W.slice(0,2)+u,Q:r.before.Q.slice(0,2)+p});
  const mapping=Array.from({length:23},(_,i)=>i);
  for(const [dst,src] of [[0,18],[15,16],[16,17],[17,15],[18,0]])mapping[dst]=src;
  const oracle=analyzeTrace({beforeEvent:r.traced.events.find(e=>e.ring),afterEvent:end,
    writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  if(r.options.verifyExit) {
    same(r.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(at('post/zero').ring.X),'000050000000');same(raw(at('post/program').ring.X),zero);
    same(raw(at('done').ring.X),'000050000000');same(markers(at('done').ring),['marker']);
    same(snapshotFromRing(at('done').ring).words,snapshotFromRing(end.ring).words);
    assert.ok(r.traced.writes.filter(w=>w.command>=post&&
      ((w.nibble%3===0&&w.nibble<36)||(Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)||
        [36,37,39,40].includes(w.nibble))).every(w=>w.before===w.value));
  }
  return {clearing,boundaries:rows.length,first,second,mapping,cycles:oracle.data.cycles,
    all23LiveAtEveryActionBoundary:true,all23StoredAtEnd:true,allExtraMarkersRemoved:true,
    other14OrdinaryUpper4ProgramAndServicesHeld:true,workingExitTested:!!r.options.verifyExit,
    repeatabilityProved:false,numericDomainProved:false,upperWordsChanged:0,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,verifyExit:true,...JSON.parse(process.env.K1_Z_RESTORED_OPTIONS||'{}')};
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS restored Z reserve:',JSON.stringify(check(r)));
  if(process.env.K1_Z_RESTORED_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,unmark,check};
