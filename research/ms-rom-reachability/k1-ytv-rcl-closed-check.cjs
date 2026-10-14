#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-ytv-rcl-closed.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const previous=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const surface=require('./k1-x1-retry-reader-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const m='9990FFFFFFF0',zero='000000000000';
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const lower=e=>['U','V','W','Q'].map(n=>raw(e.ring[n]));
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const word=previous.word,ips=previous.ips,path=previous.path;
// A zero-frame phase label has no native event; the next action is the
// same boundary, whereas the passive frame observer records both labels.
const nextStage=(r,i)=>(r.options.deepTailPhases[i]?'deep/tail-phase-':'deep/tail-')+i;
const mapping=Array.from({length:23},(_,i)=>i);
for(const [dst,src] of [[0,18],[15,16],[16,17],[17,15],[18,0]])mapping[dst]=src;

function publicSurface(o) {
  const ds=['1,','2,','3,','4,','5,'],a=surface.record(ds,o,probe.finish);
  same(a,surface.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);same(a.result,undefined);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicKeysWaitsAndDisplaysOnly:true,fixtureExcluded:true,assumedFirstSuccessfulReaderAttempts:true};
}

function frameCheck(r) {
  const original=snapshotFromRing(r.initial),at=s=>{const e=r.rows.find(x=>x.stage===s);assert.ok(e,s);return e;};
  same(r.options.deepTail,probe.defaults.deepTail);same(r.options.deepTailPhases,probe.defaults.deepTailPhases);
  same(new Set(original.words).size,23);same(r.rows.filter(x=>x.missing.length),[]);
  for(const e of r.rows) {
    const s=snapshotFromRing(e.ring);same(s.program,original.program);same(s.services,original.services);
    same(s.words.slice(1,15),original.words.slice(1,15));same(s.words.slice(19),original.words.slice(19));
    same(e.values.marker,'000FFFFFFFFF');
  }
  for(const stage of [r.options.verifyExit?'post/manual':'immediate','done']) {
    const e=at(stage);same(snapshotFromRing(e.ring).words,mapping.map(i=>original.words[i]));
    same(marks(e),['marker']);
  }
  if(r.options.verifyExit) {
    same(at('post/zero').values.X,'000050000000');same(at('post/program').values.X,zero);
    same(at('done').values.X,'000050000000');
  }
  return {boundaries:r.rows.length,all23LiveAtEveryFrameBoundary:true,all23StoredAtExit:true,
    upper4AndOther14OrdinaryAndProgramHeld:true,allExtraMarkersRemoved:true,
    workingExitTested:!!r.options.verifyExit,fullK1:false};
}

function formatter(r,stage,read,late,zeros,markers,isZero=false) {
  const seq=ips('EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE');
  seq.push(...(isZero?[0xD0,0xF2]:[0xD9]),
    ...Array.from({length:zeros+1},()=>[0xF3,0xF7,0xF1]).flat(),
    ...Array.from({length:8-zeros},()=>[0xF4,0xF6]).flat(),0xF4,0xEA,0xEC,
    0x40,0x41,isZero?0x43:0x42,0x46);
  while(!markers.includes(slots[(slots.indexOf(read.slot)+seq.length)%15]))seq.push(0xE5);
  seq.push(0xE5,0xE6,0xE8,0xE7);
  same(late.command-read.command+1,seq.length);
  path(r.traced.events.filter(e=>e.stage===stage),read.command,read.slot,seq);
}

function readPush(r,index,source,value,lateValue,zeroes,oldT) {
  const stage='deep/tail-'+index,endStage=nextStage(r,index+1);
  const at=checks.boundary(r,stage),end=checks.boundary(r,endStage),es=r.traced.events.filter(e=>e.stage===stage);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE),writes=es.filter(e=>e.ip===0xE7);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[[source,value,index===1?0xAB:0xE0],['X',lateValue,0xE3]]);
  same(writes.length,2);
  if(index===1) {
    const d6=es.filter(e=>e.ip===0xD6);same(d6.length,1);same(d6[0].slot,'U');
    same(raw(ringAt(r,d6[0].command).U,0),lateValue);
  }
  const push=checks.exactPush(r,stage,['X','Y','Z','T']);same(push.displaced,oldT);
  repack.exactCopy(r,writes[1],'V',lateValue);
  formatter(r,stage,reads[1],writes[1],zeroes,index===1?['marker','Z','V']:['marker','Z']);
  const ww=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
  same(ww.map(w=>[w.command,w.chip,w.slot,w.nibble]),
    [...['X','Y','Z','T'].map((n,i)=>[push.command+i,n]),[writes[1].command,'V']]
      .flatMap(([c,n])=>Array.from({length:12},(_,j)=>[c,3,n,1+3*j])));
  const expected=structuredClone(at.ring);
  word(expected,'X',lateValue);for(const [dst,src] of [['Y','X'],['Z','Y'],['T','Z']])word(expected,dst,raw(at.ring[src]));
  word(expected,'V',lateValue);same(end.ring,expected,'all 630 read/push endpoint tetras');
  return {stage,earlyRead:reads[0].command,push:push.command,lateRead:reads[1].command,lateV:writes[1].command};
}

function request(r,index,spec) {
  const stage='deep/tail-'+index,endStage=index===6?'return/reader-phase':nextStage(r,index+1);
  const at=checks.boundary(r,stage),end=checks.boundary(r,endStage),es=r.traced.events.filter(e=>e.stage===stage);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),spec.gates.map(n=>[n,0x9E]));
  const reads=es.filter(e=>e.ip===0xEE),copies=es.filter(e=>e.ip===0xE9),reqs=es.filter(e=>e.ip===0xA3),lates=es.filter(e=>e.ip===0xE7);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['X',spec.value,0xA1],['X',spec.value,0xE3]]);
  same([copies.length,reqs.length,lates.length],[1,1,1]);
  const req=reqs[0],late=lates[0];repack.exactCopy(r,copies[0],spec.copy,spec.value);
  repack.exactCopy(r,late,spec.late,spec.value);
  const hv=[parseInt(spec.value[2],16),spec.code%16,spec.code>>4],rh=ringAt(r,req.command);
  same(req.slot,spec.request);[28,31,34].forEach((n,i)=>{rh[spec.request][n]=hv[i];});
  same(ringAt(r,req.command+1),rh);
  same(r.traced.writes.filter(w=>w.command===req.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
    [28,31,34].map((n,i)=>[3,spec.request,n,hv[i]]));
  const ww=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
  const secondary=ww.filter(w=>w.chip===4),ack=secondary.filter(w=>w.ip===0x27),out=secondary.filter(w=>w.ip!==0x27);
  same(ack.map(w=>[w.slot,w.nibble,w.value]),[['control',31,15],['control',31,15]]);
  const first=out[0].command;
  same(out.map(w=>[w.command-first,w.ip,w.slot,w.nibble]),['X','Y','Z','T'].flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i,i===3?0x2A:0x3A,n,1+3*j])));
  same(r.traced.writes.filter(w=>w.command>=first&&w.command<first+4),out);
  path(es,req.command,spec.consumer,ips(spec.path),4);
  same(es.find(e=>e.command===req.command).otherChips[4].r[29],0);
  const old=ringAt(r,first),expectedOut=structuredClone(old);
  for(const [dst,src] of spec.pairs)word(expectedOut,dst,src===null?zero:raw(old[src]));
  same(ringAt(r,first+4),expectedOut,'exact 48-tetra secondary output and other 582 tetras held');
  if(index===5) {
    const source=es.find(e=>e.command===req.command+3).otherChips[4];
    const second=es.find(e=>e.command===req.command+4).otherChips[4];
    same([source.ip,source.slot,raw(source.m),second.ip,second.slot,raw(second.m)],
      [0x52,'X',spec.value,0x53,'Y',spec.value]);
    same(raw(expectedOut.X),zero,'equal operands subtract to exact zero');
    same([raw(expectedOut.Z),raw(expectedOut.T)],[raw(at.ring.T),raw(at.ring.T)],'old T gets two complete copies');
  }
  assert.ok(reads[1].command<first&&first+4<late.command);
  formatter(r,stage,reads[1],late,spec.zeros,spec.markers,!!spec.zero);
  const expected=structuredClone(at.ring);word(expected,spec.copy,spec.value);
  [28,31,34].forEach((n,i)=>{expected[spec.request][n]=hv[i];});expected.control[31]=15;
  const beforeOutput=structuredClone(expected);
  for(const [dst,src] of spec.pairs)word(expected,dst,src===null?zero:raw(beforeOutput[src]));
  word(expected,spec.late,spec.value);same(end.ring,expected,'all 630 full-operation endpoint tetras');
  const allowed=new Set(['3:'+copies[0].command,'3:'+req.command,'3:'+late.command,...secondary.map(w=>'4:'+w.command)]);
  same(ww.filter(w=>w.before!==w.value&&!allowed.has(w.chip+':'+w.command)),[]);
  return {stage,read:reads[0].command,reserve:copies[0].command,request:req.command,
    lateRead:reads[1].command,secondaryOutput:first,lateWrite:late.command};
}

function check(full) {
  const r=full.options.verifyExit?prefixView(full,'post/manual'):full;
  same(r.options.deepTail,probe.defaults.deepTail);same(r.options.deepTailPhases,probe.defaults.deepTailPhases);
  same(r.options.readerLeadPhase,1);
  const prefix=previous.check(prefixView(r,'deep/tail-phase-1',{deepTail:[['K','0']],deepTailPhases:[1]}));
  // Program execution may temporarily update its own control fields.
  // The research protocol is audited before the ordinary post-exit tests.
  checks.protectedFields(r,[0],['U','V','W','Q']);
  same(full.afterProgram,full.beforeProgram);
  same(full.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const at=s=>checks.boundary(r,s),operations=[];
  operations.push(readPush(r,1,'W',q,w,1,m));
  operations.push(request(r,2,{gates:['T','T'],value:w,copy:'U',request:'control',code:0x25,
    consumer:'marker',pairs:[['X','Y'],['Y','Z'],['Z','T'],['T','X']],late:'U',zeros:1,markers:['marker','Y'],
    path:'6E 5E 50 52 53 4F 24 26 28 D3 37 37 37 37 37 37 27 D4 D4 D4 D4 D4 C4 2C 3B 2B 60 37 37 37 37 27 61 3A 3A 3A 2A 39'}));
  const ns=r.traced.events.filter(e=>e.stage==='deep/tail-3'),nr=ns.filter(e=>e.ip===0xEE),nw=ns.filter(e=>e.ip===0xE7);
  same(ns.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['Z',0x9E],['control',0x9E]]);
  const ng=ns.find(e=>e.ip===0x9C);same([ng.r[23],ng.r[26],ng.r[29]],[0,0,4]);
  same(nr.map(e=>[e.slot,e.raw,e.nextIp]),[['X',u,0xAB],['X',u,0xE3]]);same(nw.length,1);
  same(ns.filter(e=>[0xE9,0xA3,0xA8].includes(e.ip)),[]);repack.exactCopy(r,nw[0],'U',u);
  formatter(r,'deep/tail-3',nr[1],nw[0],0,['marker','Y']);
  const nb=at('deep/tail-3'),ne=at('deep/tail-phase-4'),nx=structuredClone(nb.ring);word(nx,'U',u);same(ne.ring,nx);
  same(r.traced.writes.filter(w=>w.command>=nb.command&&w.command<ne.command&&w.before!==w.value&&w.command!==nw[0].command),[]);
  operations.push({stage:'deep/tail-3',readX:nr[1].command,restoreU:nw[0].command});
  operations.push(readPush(r,4,'U',u,u,0,w));
  operations.push(request(r,5,{gates:['T','T'],value:u,copy:'U',request:'control',code:0x11,
    consumer:'marker',pairs:[['X',null],['Y','Z'],['Z','T'],['T','T']],late:'U',zeros:0,markers:['marker','Y'],
    path:'6E 5E 50 52 53 4F 41 43 1D 0D FC FD FC FE FD FF F0 2F 21 32 B5 BB A7 44 D3 37 37 37 37 37 37 27 D4 D4 D4 D4 D4 C4 2C 3B 47 2B 60 37 37 37 27 61 3A 3A 3A 2A 39'}));
  same(visible(at('deep/tail-6')).slice(1),[zero,m,v,v]);
  operations.push(request(r,6,{gates:['control','control'],value:zero,copy:'X1',request:'Z',code:0x25,
    consumer:'Y',pairs:[['X','V'],['Y','Z'],['Z','T'],['T','U']],late:'X',zeros:7,zero:true,markers:['marker'],
    path:'6E 5E 50 52 53 4F 24 26 28 D3 37 37 27 D4 D4 D4 D4 D4 C4 2C 3B 2B 60 37 37 37 37 27 61 3A 3A 3A 2A 39'}));
  const cleared=at('return/reader-phase');same(visible(cleared),[zero,zero,'250'+v.slice(3),v,u]);
  same(lower(cleared),[u,u,q,p]);same(marks(cleared),['marker']);
  same(raw(at('return/read-q/attempt-0/read-prep-0').ring.X),v);
  same(visible(at('return/save-q')).slice(1),[q,zero,v,w]);
  same(raw(at('return/first/push-marker-0').ring.U,0),q);
  const first=checks.exactPush(r,'return/first/push',['T','U','V','W']);same(first.displaced,q);
  same(lower(at('return/v-to-t-0')),[w,u,u,p]);
  same(raw(at('return/second/push-marker-0').ring.T),v);
  const second=checks.exactPush(r,'return/second/push',['T','U','V','W']);same(second.displaced,u);
  const end=at('done'),initial=r.traced.events.find(e=>e.ring),original=snapshotFromRing(initial.ring);
  same(snapshotFromRing(end.ring).words,mapping.map(i=>original.words[i]));same(marks(end),['marker']);
  const oracle=analyzeTrace({beforeEvent:initial,afterEvent:end,writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');
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
  return {prefix,boundaries:rows.length,operations,first,second,cycles:oracle.data.cycles,
    all23LiveAtEveryActionBoundary:true,all23StoredAtExit:true,allExtraMarkersRemoved:true,
    upper4AndOther14OrdinaryAndProgramHeld:true,workingExitTested:!!full.options.verifyExit,
    newUpperCapacity:false,unboundedRepeatProved:false,wholeNumericDomainProved:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,verifyExit:true,...JSON.parse(process.env.K1_YTV_CLOSED_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(publicSurface(o)));
  if(!process.env.K1_YTV_SKIP_FRAME)console.log('PASS frame boundaries:',JSON.stringify(frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS exact closed Y/T/V route:',JSON.stringify(check(r)));
  if(process.env.K1_YTV_CLOSED_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={mapping,publicSurface,frameCheck,formatter,readPush,request,check};
