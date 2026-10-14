#!/usr/bin/env node
'use strict';
// A conditional closed exit after actually reading long upper a. This is
// not a new upper exchange: all four upper words are fixed at the endpoint.
const assert=require('node:assert/strict');
const probe=require('./k1-zv-nop-closed.cjs');
const nop=require('./k1-zv-nop-release-check.cjs');
const previous=require('./k1-ytv-rcl-closed-check.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const zw=require('./k1-zw-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=assert.deepEqual,zero='000000000000',m='9990FFFFFFF0';
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const visible=e=>['X','Y','Z','T'].map(n=>raw(e.ring[n]));
const mapping=Array.from({length:23},(_,i)=>i);
for(const [dst,src] of [[0,17],[17,18],[18,0]])mapping[dst]=src;
const writes=(r,at,end)=>r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
const key=w=>[w.command,w.chip,w.slot,w.nibble,w.value];
const ordered=xs=>xs.toSorted((a,b)=>a[0]-b[0]||a[1]-b[1]||a[3]-b[3]);
const copy=(command,chip,slot,value)=>[...value].reverse().map((v,i)=>[command,chip,slot,1+3*i,parseInt(v,16)]);

function frameCheck(r) {
  const original=snapshotFromRing(r.initial),at=s=>{const e=r.rows.find(x=>x.stage===s);assert.ok(e,s);return e;};
  same(new Set(original.words).size,23);same(r.rows.filter(x=>x.missing.length),[]);
  for(const e of r.rows) {
    const s=snapshotFromRing(e.ring);same(s.program,original.program);same(s.services,original.services);
    same(s.words.slice(1,15),original.words.slice(1,15));same(s.words.slice(19),original.words.slice(19));
    same(e.values.marker,'000FFFFFFFFF');
  }
  for(const stage of [r.options.verifyExit?'post/manual':'immediate','done']) {
    const e=at(stage);same(snapshotFromRing(e.ring).words,mapping.map(i=>original.words[i]));same(marks(e),['marker']);
  }
  if(r.options.verifyExit) {
    same(at('post/zero').values.X,'000050000000');same(at('post/program').values.X,zero);
    same(at('done').values.X,'000050000000');
  }
  return {boundaries:r.rows.length,all23Live:true,all23StoredAtExit:true,upper4Fixed:true,
    allExtraMarkersRemoved:true,workingExitTested:!!r.options.verifyExit,fullK1:false};
}

function max(r) {
  const stage='w/tail-0',at=checks.boundary(r,stage),end=checks.boundary(r,'w/tail-phase-1');
  const es=r.traced.events.filter(e=>e.stage===stage),ww=writes(r,at,end);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  assert.ok(Number(r.options.fullUpper[0])<Number(r.options.values[3]),'fixture requires a < u');
  const a=r.before.P7.slice(2),u=r.before.U.slice(2);
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['T',0x9E],['T',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE),saves=es.filter(e=>e.ip===0xE9),reqs=es.filter(e=>e.ip===0xA3),lates=es.filter(e=>e.ip===0xE7);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['X',a,0xA1],['X',a,0xE3]]);
  same([saves.length,reqs.length,lates.length],[1,1,1]);
  const save=saves[0],req=reqs[0],late=lates[0];same(req.slot,'control');
  repack.exactCopy(r,save,'U',a);repack.exactCopy(r,late,'V',a);
  zw.formatter(r,stage,reads[1],late,'V',['marker','Z']);
  const hv=[parseInt(a[2],16),6,3],reqRing=ringAt(r,req.command);
  [28,31,34].forEach((n,i)=>{reqRing.control[n]=hv[i];});same(ringAt(r,req.command+1),reqRing);
  const tertiary=ww.filter(w=>w.chip===5),ack=tertiary.filter(w=>w.ip===0xFD),out=tertiary.filter(w=>w.ip!==0xFD);
  same(ack.map(w=>[w.slot,w.nibble,w.value]),[['control',31,15]]);same(out.length,12);
  const first=out[0].command;same(out.map(w=>[w.command,w.ip,w.slot,w.nibble,w.value]),
    copy(first,5,'X',u).map(([c,,slot,n,v])=>[c,0xFF,slot,n,v]));
  const old=ringAt(r,first),expectedOut=structuredClone(old);same(raw(old.Y),u);deep.word(expectedOut,'X',u);
  same(ringAt(r,first+1),expectedOut,'max copies Y to X and changes no other ring tetra');
  assert.ok(reads[1].command<first&&first<late.command,'late copy holds a sampled before max');
  same(ordered(ww.map(key)),ordered([...copy(save.command,3,'U',a),
    ...[28,31,34].map((n,i)=>[req.command,3,'control',n,hv[i]]),
    [ack[0].command,5,'control',31,15],...copy(first,5,'X',u),...copy(late.command,3,'V',a)]));
  const expected=structuredClone(at.ring);deep.word(expected,'U',a);deep.word(expected,'X',u);
  [28,31,34].forEach((n,i)=>{expected.control[n]=hv[i];});expected.control[31]=15;
  same(end.ring,expected,'all 630 max endpoint tetras');
  return {request:req.command,tertiaryYtoX:first,lateAtoV:late.command,fixtureOrder:'a < u'};
}

function subtract(r) {
  // Rename only the passive journal to reuse the previously audited exact
  // equal-subtraction contract. No emulator state is imported or edited.
  const renamed={...r,traced:{...r.traced,events:r.traced.events.map(e=>({...e,
    stage:e.stage==='w/tail-1'?'deep/tail-5':e.stage==='w/tail-2'?'deep/tail-6':e.stage}))}};
  const u=r.before.U.slice(2);
  return previous.request(renamed,5,{gates:['T','T'],value:u,copy:'U',request:'control',code:0x11,
    consumer:'marker',pairs:[['X',null],['Y','Z'],['Z','T'],['T','T']],late:'U',zeros:0,markers:['marker','Y'],
    path:'6E 5E 50 52 53 4F 41 43 1D 0D FC FD FC FE FD FF F0 2F 21 32 B5 BB A7 44 D3 37 37 37 37 37 37 27 D4 D4 D4 D4 D4 C4 2C 3B 47 2B 60 37 37 37 27 61 3A 3A 3A 2A 39'});
}

function push(r,index) {
  const stage='w/tail-'+index,endStage=index===4?'done':'w/tail-'+(index+1);
  const at=checks.boundary(r,stage),end=checks.boundary(r,endStage),es=r.traced.events.filter(e=>e.stage===stage);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  const v=r.before.V.slice(2),r1=r.beforeRegisters[1],value=index===2?v:r1;
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[[['control','T','U'][index-2],0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE),lates=es.filter(e=>e.ip===0xE7);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),index===2?[['T',v,0xF0],['X',v,0xE3]]:
    [['X',index===3?v:r1,0xAB],['X',r1,0xE3]]);
  same(lates.length,2);same(es.filter(e=>[0xE9,0xA3,0xD4].includes(e.ip)),[]);
  const d6=es.filter(e=>e.ip===0xD6);
  if(index===2)same(d6,[]);
  else {same(d6.length,1);same(d6[0].slot,'V');same(raw(ringAt(r,d6[0].command).V,0),r1);}
  const shifted=checks.exactPush(r,stage,['X','Y','Z','T']);same(shifted.displaced,raw(at.ring.T));
  const late=lates[1],target=index===2?'V':'X';repack.exactCopy(r,late,target,value);
  if(index===2)previous.formatter(r,stage,reads[1],late,0,['marker','Z']);
  const expected=structuredClone(at.ring);deep.word(expected,'X',value);
  for(const [dst,src] of [['Y','X'],['Z','Y'],['T','Z']])deep.word(expected,dst,raw(at.ring[src]));
  deep.word(expected,target,value);same(end.ring,expected,'all 630 reader/push endpoint tetras');
  const ww=writes(r,at,end);
  same(ww.map(key),[...['X','Y','Z','T'].flatMap((n,i)=>copy(shifted.command+i,3,n,raw(expected[n]))),
    ...copy(late.command,3,target,value)]);
  return {stage,earlyRead:reads[0].command,push:shifted.command,lateRead:reads[1].command,lateWrite:late.command,target};
}

function check(full) {
  const r=full.options.verifyExit?prefixView(full,'post/manual'):full;
  same(r.options.afterW,probe.defaults.afterW);same(r.options.afterWPhases,probe.defaults.afterWPhases);
  const prefix=nop.check(prefixView(r,'w/tail-0',{afterW:[],afterWPhases:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q']);same(full.afterProgram,full.beforeProgram);
  same(full.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const ops=[max(r),subtract(r),push(r,2),push(r,3),push(r,4)];
  const u=r.before.U.slice(2),v=r.before.V.slice(2),a=r.before.P7.slice(2),at=s=>checks.boundary(r,s);
  same(visible(at('w/tail-0')),[a,u,m,v]);same(visible(at('w/tail-phase-1')),[u,u,m,v]);
  same(visible(at('w/tail-2')),[zero,m,v,v]);same(visible(at('w/tail-3')),[v,zero,m,v]);
  const initial=r.traced.events.find(e=>e.ring),end=at('done');
  const oracle=analyzeTrace({beforeEvent:initial,afterEvent:end,writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');same(marks(end),['marker']);
  const rows=repack.boundaryLosses(full);same(rows.filter(e=>e.missing.length),[]);
  if(full.options.verifyExit) {
    same(full.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(full,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(full,'post/program').ring.X),zero);
    const done=checks.boundary(full,'done');same(raw(done.ring.X),'000050000000');same(marks(done),['marker']);
    same(snapshotFromRing(done.ring).words,snapshotFromRing(end.ring).words);
    same(full.traced.writes.filter(w=>w.command>=end.command&&w.before!==w.value&&
      ((w.nibble%3===0&&w.nibble<36)||(Object.hasOwn(full.before,w.slot)&&w.nibble%3===1)||[36,37,39,40].includes(w.nibble))),[]);
  }
  return {prefix,boundaries:rows.length,operations:ops,cycles:oracle.data.cycles,
    all23Live:true,all23StoredAtExit:true,upper4AndOther14OrdinaryProgramAndServicesHeld:true,
    allExtraMarkersRemoved:true,workingExitTested:!!full.options.verifyExit,
    newUpperCapacity:false,repeatabilityProved:false,wholeNumericDomainProved:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,verifyExit:true,...JSON.parse(process.env.K1_ZV_CLOSED_OPTIONS||'{}')};
  console.log('PASS surface:',JSON.stringify(deep.surface(o,probe.finish)));
  if(!process.env.K1_ZV_CLOSED_SKIP_FRAME)console.log('PASS frames:',JSON.stringify(frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS native:',JSON.stringify(check(r)));
  if(process.env.K1_ZV_CLOSED_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={mapping,frameCheck,max,subtract,push,check};
