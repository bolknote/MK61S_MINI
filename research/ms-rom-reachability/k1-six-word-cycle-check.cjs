#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const cycle=require('./k1-six-word-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const hist=require('./k1-puhov-ring-probe.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {snapshotFromRing,MS_SLOTS}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b)=>assert.deepEqual(a,b),zero='000000000000';
const defaults={...hist.defaults,values:['-1.2345678E-42','822','833','844'],phaseOffset:1};
function operation(c,o={},record=()=>{}) {
  cycle.finish(c,o,record);
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.press('Сx').runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
const run=(o={})=>cap.run({...defaults,...o},operation,['tail-0','tail-1','tail-3','tail-4','tail-5','tail-6']);
function rotation(r,stage,slots) {
  const es=r.traced.events.filter(e=>e.stage===stage),lo=es[0].command,hi=es.at(-1).command+1;
  assert.ok(es.every(e=>e.otherChips?.[4]),'complete secondary trace');
  const writes=r.traced.writes.filter(w=>w.command>=lo&&w.command<hi&&w.chip===4&&
    ((w.ip===0x3A&&slots.slice(0,3).includes(w.slot))||(w.ip===0x2A&&w.slot===slots[3])));
  same(writes.map(w=>[w.ip,w.slot,w.nibble]),slots.flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i===3?0x2A:0x3A,n,1+3*j])));
  const first=writes[0].command,expected=ringAt(r,first),old=structuredClone(expected);
  slots.forEach((n,i)=>{for(let j=0;j<12;j++)expected[n][1+3*j]=old[slots[(i+1)%4]][1+3*j];});
  same(ringAt(r,first+4),expected,'exact four-word rotation among all 630 tetras');
  same(es.filter(e=>e.command>=first&&e.command<first+4).map(e=>
    [e.otherChips[4].ip,e.otherChips[4].slot]),slots.map((n,i)=>[i===3?0x2A:0x3A,n]));
  if(stage==='tail-0') {
    const pre=es.filter(e=>e.command>=first-16&&e.command<first).map(e=>e.otherChips[4]);
    same(pre.map(e=>[e.ip,e.slot]),[
      ...['V','W','Q','P7','P8'].map(n=>[0xD4,n]),[0xC4,'P9'],[0x2C,'P10'],[0x3B,'marker'],
      [0x2B,'control'],[0x60,'X1'],...['X','Y','Z','T'].map(n=>[0x37,n]),[0x27,'U'],[0x61,'V']]);
    same([pre[0].l,pre[0].s1,...[37,38,40,41].map(i=>pre[0].r[i])],[1,9,4,0,13,6]);
    same([0,1,2].map(i=>pre[0].st[36+i]+16*pre[0].st[39+i]),[0x29,0x3A,0x3A]);
    const before=ringAt(r,first-16);
    same(raw(pre[0].r,2),raw(before.W));same(raw(pre[0].r,1),raw(before.Q));
    same(before.T[22],15);same(before.U[31],15);
    assert.ok(['X','Y','Z'].every(n=>before[n][22]!==15));
  }
  return {command:first,slots};
}
function markerRemoval(r) {
  const es=r.traced.events.filter(e=>e.stage==='tail-3'),start=es.findIndex(e=>e.ip===0x9C&&e.slot==='T');
  assert.ok(start>=0);const route=es.slice(start,start+26);
  const ips=[0x9C,0x9E,0x9F,0xA0,...Array(6).fill(0xE5),0xE6,0xED,0xEE,0xA1,
    0xE5,0xE6,0xE9,...Array(8).fill(0xA2),0xA3];
  const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  same(route.map(e=>[e.ip,e.slot]),ips.map((ip,i)=>[ip,slots[(6+i)%15]]));
  same([route[0].r[30],route[0].r[33]],[2,3]);
  const ee=route[12],copy=route[16],v=r.before.V.slice(2);
  same(ee.raw,v);same(raw(copy.r,0),v);
  const expected=ringAt(r,copy.command);
  same(expected.U[22],15);
  [...v].reverse().forEach((n,j)=>{expected.U[1+3*j]=parseInt(n,16);});
  same(ringAt(r,copy.command+1),expected,'E9 removes U marker by exact X-to-U copy among all 630 tetras');
  const lastRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);
  assert.ok(lastRead);same([lastRead.slot,lastRead.raw],['X',v]);
  const late=es.find(e=>e.command>lastRead.command&&e.ip===0xE7);
  assert.ok(late&&['X','V'].includes(late.slot));same(raw(late.r,0),v);
  const lateExpected=ringAt(r,late.command);
  [...v].reverse().forEach((n,j)=>{lateExpected[late.slot][1+3*j]=parseInt(n,16);});
  same(ringAt(r,late.command+1),lateExpected,'SIGN return copies old v exactly to X or V');
  return {entry:route[0].command,read:ee.command,copy:copy.command,request:route.at(-1).command,
    lateCopy:late.command,lateTarget:late.slot};
}
function check(r) {
  const post=r.options.verifyExit?checks.boundary(r,'post/program').command:Infinity;
  checks.protectedFields({...r,traced:{...r.traced,
    events:r.traced.events.filter(e=>e.command<post),
    writes:r.traced.writes.filter(w=>w.command<post),
    primitives:r.options.verifyExit?r.traced.events.filter(e=>e.command<post&&[0xC7,0xC8].includes(e.ip)).map(e=>e.ip):
      r.traced.primitives}},[0],['U','V','W','Q','P7','P8']);
  if(r.options.verifyExit) {
    // Program execution may move the M3 instruction stream. Neither stored
    // numeric lane nor either numeric service field may be changed by it.
    assert.ok(r.traced.writes.filter(w=>w.command>=post&&
      ((w.nibble%3===0&&w.nibble<36)||(MS_SLOTS.includes(w.slot)&&w.nibble%3===1)||
        [36,37,39,40].includes(w.nibble))).every(w=>w.value===w.before));
  }
  const [u,v,w,q,a,b]=['U','V','W','Q','P7','P8'].map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0],end=checks.boundary(r,'done');
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:u));
  same(r.after,{...r.before,U:r.before.U.slice(0,2)+(r.options.returnedQ?q:w),
    V:r.before.V.slice(0,2)+(r.options.returnedQ?w:v),
    W:r.before.W.slice(0,2)+(r.options.returnedQ?v:q),Q:r.before.Q.slice(0,2)+a,
    P7:r.before.P7.slice(0,2)+b,P8:r.before.P8.slice(0,2)+p});
  const clean=checks.boundary(r,r.options.verifyExit?'post/manual':'done');
  same(['X','Y','Z','T'].map(n=>raw(clean.ring[n])),[zero,zero,zero,zero]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker']);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  assert.equal(new Set(original).size,23);assert.ok(!original.includes(zero));
  const seen=new Set();let boundaries=0;
  for(const e of r.traced.events)if(e.ring&&!seen.has(e.stage)) {
    seen.add(e.stage);boundaries++;
    const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    for(const n of original)assert.ok(live.includes(n),'lost '+n+' at '+e.stage);
  }
  const rotations=[rotation(r,'tail-0',['W','Q','P7','P8']),rotation(r,'tail-1',['X','Y','Z','T'])];
  const cleanup=markerRemoval(r);
  const loads=(r.options.clearByZero?['tail-4','tail-6']:['tail-4','tail-5'])
    .map(s=>checks.exactPush(r,s,['X','Y','Z','T']));
  if(r.options.verifyExit) {
    same(r.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(r,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(r,'post/program').ring.X),zero);
    same(raw(end.ring.X),'000050000000');
  }
  const cycles=r.options.returnedQ?[['P0','Ms.P8','Ms.P7','Ms.Q','Ms.U'],['Ms.V','Ms.W']]:
    [['P0','Ms.P8','Ms.P7','Ms.Q','Ms.W','Ms.U']];
  let qReturn;
  if(r.options.returnedQ) {
    const b=checks.boundary(r,'return-q/blind-duplicate');
    same(raw(b.ring.X),q);same(raw(b.ring.U),w);same(raw(b.ring.V),v);
    assert.ok([q,v].includes(raw(b.ring.W)),'discarded W has another copy');
    qReturn=checks.exactPush(r,'return-q/push',['T','U','V','W']);
  }
  return {phase:r.options.phaseOffset,boundaries,cycles,
    scratchRetryAlignment:r.options.alignScratchRetries??!!r.options.returnedQ,
    all23StoredAtExit:true,all23RetainedAtEveryBoundary:true,allExtraMarkersRemoved:true,
    programAndOther14OrdinaryAndUpper2Held:true,rotations,cleanup,loads,qReturn,
    workingExitTested:!!r.options.verifyExit,fullK1:false};
}
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,cycle.finish);
  same(a,control.record(ds,{...o,incoming:'unread',values:['unread'],fullUpper:['unread'],p3:'unread'},cycle.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempts:1};
}
function diagnose(r) {
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words,seen=new Set();
  const boundaries=r.traced.events.filter(e=>e.ring&&!seen.has(e.stage)&&(seen.add(e.stage),true));
  const lost=boundaries.map(e=>{const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    return {stage:e.stage,command:e.command,missing:original.filter(x=>!live.includes(x))};}).filter(e=>e.missing.length);
  const corrupt=r.traced.writes.find(w=>w.nibble%3===2&&w.value!==w.before);
  const stageFor=command=>boundaries.findLast(e=>e.command<=command)?.stage;
  return {options:r.options,firstLost:lost[0],lastLost:lost.at(-1),
    firstProgramWrite:corrupt&&{stage:stageFor(corrupt.command),...corrupt},
    before:r.before,after:r.after,registers:r.afterRegisters,
    programHeld:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_SIX_OPTIONS||'{}');
  console.log('PASS keyboard surface:',JSON.stringify(surface({clearByZero:o.clearByZero,returnedQ:o.returnedQ})));
  const r=run(o);
  if(process.env.K1_SIX_DIAGNOSTIC)console.log('DIAGNOSTIC only:',JSON.stringify(diagnose(r)));
  else console.log('PASS closed upper permutation:',JSON.stringify(check(r)));
  if(process.env.K1_SIX_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,operation));
}
module.exports={defaults,operation,run,check,surface,rotation,markerRemoval,diagnose};
