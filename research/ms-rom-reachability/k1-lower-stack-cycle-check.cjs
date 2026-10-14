#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const cycle=require('./k1-lower-stack-cycle.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {analyzeTrace}=require('./k1-permutation-oracle.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const same=(a,b)=>assert.deepEqual(a,b);
function expected(r) {
  const [u,v,w]=['U','V','W'].map(n=>r.before[n].slice(2));
  return {registers:r.beforeRegisters.map((x,i)=>i===0?w:x),
    ms:{...r.before,U:r.before.U.slice(0,2)+r.beforeRegisters[0],
      V:r.before.V.slice(0,2)+u,W:r.before.W.slice(0,2)+v}};
}
function check(r) {
  const e=expected(r);same(r.afterRegisters,e.registers);same(r.after,e.ms);
  checks.protectedFields(r,[0],['U','V','W']);
  const start=checks.boundary(r,'cycle-push'),end=checks.boundary(r,'done');
  same(['X','Y','Z','T'].map(n=>raw(start.ring[n])),
    ['0000F0000000',r.before.W.slice(2),r.beforeRegisters[0],r.beforeRegisters[0]]);
  const push=checks.exactPush(r,'cycle-push',['T','U','V','W']);
  same(push.displaced,r.before.W.slice(2));
  const next=checks.boundary(r,'cycle-tail-0');
  same(['X','Y','Z','T'].map(n=>raw(next.ring[n])),
    ['0000F0000000',r.before.W.slice(2),r.beforeRegisters[0],r.beforeRegisters[9]]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker']);
  const mapping=Array.from({length:23},(_,i)=>i);
  mapping[0]=17;mapping[15]=0;mapping[16]=15;mapping[17]=16;
  const audit=analyzeTrace({beforeEvent:r.traced.events.find(e=>e.ring),afterEvent:end,
    writes:r.traced.writes,expectedMapping:mapping});
  assert.equal(audit.fixture.distinct,true);assert.equal(audit.data.bijection,true);
  assert.equal(audit.fixedMapping.status,'matches_this_fixture');
  return {phase:r.options.phaseOffset??0,p0:r.afterRegisters[0],
    lower:['U','V','W','Q'].map(n=>r.after[n].slice(2)),push,
    all23Permutation:true,other14RegistersHeld:true,otherFiveMsHeld:true,
    programAndServiceHeld:true,extraMarkersRemoved:true};
}
function repeated(c,o={},record=()=>{}) {
  for(let i=0;i<4;i++) {
    if(i){record('between-'+i);c.runFrames(2);}
    cycle.finish(c,{...o,phaseOffset:i?0:(o.phaseOffset??0)},s=>record('cycle'+i+'/'+s));
  }
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.press('Сx').runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
function compact(o={},operation=cycle.finish,restore=false) {
  o={...historical.defaults,...o};
  const c=capture.prepare(o),before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  aligned(c);operation(c,o);c.runFrames(3);aligned(c);
  const after=fullMsPages(c),afterRegisters=registers(c),afterProgram=program(c),visible=keyboard.stack(c);
  const r={before,beforeRegisters,beforeProgram,after,afterRegisters,afterProgram};
  const e=restore?{ms:before,registers:beforeRegisters}:expected(r);
  same(after,e.ms);same(afterRegisters,e.registers);same(afterProgram,beforeProgram);
  if(o.verifyExit)same(visible.X,'000050000000');
  return {options:o,restored:restore,endpointOnly:true,
    sha256:createHash('sha256').update(JSON.stringify(c)).digest('hex')};
}
function keyboardSurface(o={}) {
  const record=o.reader==='x1-retry'?
    (o,fn)=>require('./k1-x1-retry-reader-check.cjs').record(['1,'],o,fn).actions:keyboard.record;
  const actions=record(o,cycle.finish);
  same(actions,record({...o,incoming:'not read',values:['not read'],fullUpper:['not read']},cycle.finish));
  const keys=actions.filter(a=>a[0]==='key').length;
  const frames=keys*2+actions.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0);
  const expected=o.reader==='x1-retry'?[63,499]:o.reader==='zero-nop'?[42,367]:[37,412];expected[1]+=o.phaseOffset??0;
  same([keys,frames],expected);
  keyboard.record({verifyExit:true},repeated);
  return {keys,frames,noHiddenReads:true,publicDisplay:o.reader==='x1-retry',
    ...(o.reader==='x1-retry'?{assumedSuccessfulAttempt:1}:{}),betweenCycles:2};
}
function negativeWideW(r) {
  same(r.options.values,['811','12345678','833','844']);
  const w=r.before.W.slice(2),lost=['U','V'].map(n=>r.before[n].slice(2));
  const records=[];
  for(const [stage,slot] of [['read-oldest/0','U'],['read-oldest/1','V']]) {
    const e=r.traced.events.find(e=>e.stage===stage&&e.ip===0xE7&&e.slot===slot);assert.ok(e);
    const expected=ringAt(r,e.command);
    [...w].reverse().forEach((v,j)=>{expected[slot][1+3*j]=parseInt(v,16);});
    same(ringAt(r,e.command+1),expected);
    same(r.traced.writes.filter(x=>x.command===e.command).map(x=>[x.chip,x.slot,x.nibble]),
      Array.from({length:12},(_,i)=>[3,slot,1+3*i]));
    records.push({stage,slot,command:e.command});
  }
  const end=checks.boundary(r,'cycle-retain-a');
  const live=[...snapshotFromRing(end.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  assert.ok(lost.every(v=>!live.includes(v)));
  const e=expected(r);e.ms.V=r.before.V.slice(0,2)+w;e.ms.W=r.before.W.slice(0,2)+w;
  same(r.after,e.ms);same(r.afterRegisters,e.registers);same(r.afterProgram,r.beforeProgram);
  return {validCycle:false,wideSourceW:w,lostBankAndVisibleWords:lost,records,
    failureBeforeNewPush:true,programHeld:true};
}
function main() {
  const o=JSON.parse(process.env.K1_CYCLE_OPTIONS||'{}');
  console.log('PASS keyboard surface:',JSON.stringify(keyboardSurface(o)));
  if(process.env.K1_CYCLE_COMPACT) {
    console.log('PASS compact:',JSON.stringify(compact(JSON.parse(process.env.K1_CYCLE_OPTIONS||'{}'),
      process.env.K1_CYCLE_REPEAT?repeated:cycle.finish,!!process.env.K1_CYCLE_REPEAT)));return;
  }
  if(process.env.K1_CYCLE_NEGATIVE_WIDE) {
    const r=cycle.run({values:['811','12345678','833','844']});
    console.log('PASS wide-W negative control:',JSON.stringify(negativeWideW(r)));return;
  }
  const r=cycle.run(o);
  console.log('PASS exact cycle:',JSON.stringify(check(r)));
  const state=JSON.parse(JSON.stringify(r.calc));
  r.traced.events.length=r.traced.writes.length=0;
  if(process.env.K1_CYCLE_UNOBSERVED)console.log('PASS full observer-free state:',
    keyboard.compareUnobserved(state,r.options,cycle.finish));
}
if(require.main===module)main();
module.exports={expected,check,repeated,compact,keyboardSurface,negativeWideW};
