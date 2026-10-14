#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zero-rotate-stack-close.cjs');
const rotate=require('./k1-u-reserve-zero-rotate-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const zero='000000000000',m='9990FFFFFFF0';
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const word=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));

function surface(o={}) {
  o={...probe.defaults,...o};
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}

function check(full) {
  const r=full.options.verifyExit?prefixView(full,'post/manual'):full;
  assert.equal(r.options.closeSteps??6,6);
  const prefix=rotate.check(r,{beforeDropStage:'close/lift-u/phase'});
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.nibble<37&&w.before!==w.value),[]);
  const [u,v,w,q,a,b]=['U','V','W','Q','P7','P8'].map(n=>r.before[n].slice(2));
  const p=r.beforeRegisters[0],one=r.beforeRegisters[1];
  const at=s=>checks.boundary(r,s),es=s=>r.traced.events.filter(e=>e.stage===s);
  const end=at('done'),begin=at('close/lift-u'),savedU=at('close/swap-q'),swapped=at('close/save-q');
  const savedQ=at('close/drop-z'),oneMark=at('close/drop-t');
  const allowed=new Set();
  function permit(chip,command){allowed.add(chip+':'+command);}
  function copy(e,target,value){repack.exactCopy(r,e,target,value);permit(3,e.command);}
  function request(stage,value,opcode,gate,target,lateTarget) {
    const ee=es(stage),reads=ee.filter(e=>e.ip===0xEE);
    assert.ok(ee.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
    same(ee.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[[gate,0x9E],[gate,0x9E]]);
    same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['X',value,0xA1],['X',value,0xE3]]);
    const saves=ee.filter(e=>e.ip===0xE9);same(saves.length,1);copy(saves[0],target,value);
    const requests=ee.filter(e=>e.ip===0xA3);same(requests.length,1);const req=requests[0];
    same(req.slot,'control');const expected=ringAt(r,req.command),values=[parseInt(value[2],16),opcode%16,opcode>>4];
    [28,31,34].forEach((n,j)=>{expected.control[n]=values[j];});
    same(ringAt(r,req.command+1),expected,'only three request tetras');
    same(r.traced.writes.filter(x=>x.command===req.command).map(x=>[x.chip,x.slot,x.nibble,x.value]),
      [28,31,34].map((n,j)=>[3,'control',n,values[j]]));permit(3,req.command);
    const lates=ee.filter(e=>e.ip===0xE7);same(lates.length,1);copy(lates[0],lateTarget,value);
    return {read:reads[0].command,save:saves[0].command,request:req.command,
      lateRead:reads[1].command,late:lates[0].command};
  }
  function secondary(stage,op,targets,sources,ackValues) {
    const ee=es(stage),lo=ee[0].command,hi=ee.at(-1).command+1;
    const all=r.traced.writes.filter(x=>x.command>=lo&&x.command<hi&&x.chip===4);
    const ack=all.filter(w=>w.ip===0x27),out=all.filter(w=>w.ip!==0x27);
    same(ack.map(w=>[w.slot,w.nibble,w.before,w.value]),ackValues.map(x=>['control',31,x,15]));
    const first=out[0].command;
    same(out.map(w=>[w.command-first,w.ip,w.slot,w.nibble]),targets.flatMap((n,i)=>
      Array.from({length:12},(_,j)=>[i,i===targets.length-1?0x2A:(targets.length===2?0x4E:0x3A),n,1+3*j])));
    same(r.traced.writes.filter(w=>w.command>=first&&w.command<first+targets.length),out,'no concurrent writer in secondary output');
    const old=ringAt(r,first),expected=structuredClone(old);
    targets.forEach((n,i)=>word(expected,n,raw(old[sources[i]])));
    same(ringAt(r,first+targets.length),expected,'exact connected secondary output, all 630 tetras');
    const native=ee.filter(e=>e.command>=op.request&&e.command<=first+targets.length);
    same([native[0].otherChips[4].ip,native[0].otherChips[4].slot,native[0].otherChips[4].r[29]],
      [0x6E,'marker',0]);
    same(native.slice(0,5).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
      [[0x6E,'marker'],[0x5E,'control'],[0x50,'X1'],[0x52,'X'],[0x53,'Y']]);
    same([raw(native[3].otherChips[4].m),raw(native[4].otherChips[4].m)],
      targets.length===2?[u,q]:[zero,u]);
    same([native.at(-1).otherChips[4].ip,native.at(-1).otherChips[4].slot],
      [0x39,targets.length===2?'Z':'U']);
    if(targets.length===2) {
      const ips='6E 5E 50 52 53 4F 41 43 4D 60 37 37 37 37 37 37 27 61 4E 2A 39'.split(' ').map(x=>parseInt(x,16));
      same(native.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),ips.map((ip,i)=>[ip,slots[i%15]]));
    }
    all.forEach(w=>permit(4,w.command));
    return {consumer:op.request,output:first,return:first+targets.length};
  }
  const lift=request('close/lift-u',zero,0x10,'U','V','X');
  const liftOutput=secondary('close/lift-u',lift,['X','Y','Z','T'],['Y','Z','T','T'],[0,15]);
  same(lift.late+1,liftOutput.output,'the late zero precedes the actual 0+u result');
  const afterLift=at('close/save-u'),expectedLift=structuredClone(begin.ring);
  for(const [n,value] of Object.entries({X:u,Y:q,Z:m,T:m,V:zero,control:'1F0000000000'}))word(expectedLift,n,value);
  same(afterLift.ring,expectedLift,'complete lift endpoint');same(marks(afterLift),['T','Z','marker']);

  function nop(stage,value,early) {
    const ee=es(stage),reads=ee.filter(e=>e.ip===0xEE),writes=ee.filter(e=>e.ip===0xE7);
    same(ee.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E],['T',0x9E]]);
    const gate=ee.find(e=>e.ip===0x9C);same([gate.r[23],gate.r[26],gate.r[29]],[0,0,4]);
    same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['V',early,0xAB],['X',value,0xE3]]);
    same(ee.filter(e=>[0xE9,0xA3,0xA8].includes(e.ip)),[]);same(writes.length,1);
    copy(writes[0],'V',value);
    return {read:reads[1].command,write:writes[0].command};
  }
  const saveU=nop('close/save-u',u,zero),expectedSavedU=structuredClone(afterLift.ring);
  word(expectedSavedU,'V',u);same(savedU.ring,expectedSavedU,'first NOP only reserves u in V');
  const swap=request('close/swap-q',u,0x14,'T','U','V');
  const swapOutput=secondary('close/swap-q',swap,['X','Y'],['Y','X'],[4]);
  same(swap.lateRead+1,swapOutput.output,'primary reads old X before the secondary swap');
  assert.ok(swap.late>swapOutput.return,'late V copy is the old u, not the new q');
  const expectedSwapped=structuredClone(savedU.ring);
  for(const [n,value] of Object.entries({X:q,Y:u,U:u,control:'1F'+u[2]+'000000000'}))word(expectedSwapped,n,value);
  same(swapped.ring,expectedSwapped,'complete swap endpoint, all 630 tetras');
  const saveQ=nop('close/save-q',q,u),expectedSavedQ=structuredClone(swapped.ring);
  word(expectedSavedQ,'V',q);same(savedQ.ring,expectedSavedQ,'second NOP only stores q in V');

  const drops=[];
  for(const [stage,early,value] of [['close/drop-z','X',q],['close/drop-t','W',p]]) {
    const ee=es(stage),reads=ee.filter(e=>e.ip===0xEE),loads=ee.filter(e=>e.ip===0xD6);
    same(ee.filter(e=>[0xE9,0xA3].includes(e.ip)),[]);
    same(reads.map(e=>[e.slot,e.raw]),[[early,value],['X',one]]);same(reads[1].nextIp,0xE3);
    same(loads.length,1);same([loads[0].slot,raw(loads[0].m,0)],['V',one]);
    const push=checks.exactPush(r,stage,['X','Y','Z','T']);same(push.displaced,m);
    for(let i=0;i<4;i++)permit(3,push.command+i);
    const lates=ee.filter(e=>e.ip===0xE7&&e.command>reads[1].command);same(lates.length,1);copy(lates[0],'X',one);
    drops.push({stage,read:loads[0].command,push,late:lates[0].command});
  }
  same(es('close/drop-z').filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['T',0x9E]]);
  same(es('close/drop-t').filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['U',0x9D],['control',0x9E]]);
  const expectedOne=structuredClone(savedQ.ring);
  for(const [n,value] of Object.entries({X:one,Y:q,Z:u,T:m}))word(expectedOne,n,value);
  same(oneMark.ring,expectedOne);same(marks(oneMark),['T','marker']);
  const expectedEnd=structuredClone(oneMark.ring);
  for(const [n,value] of Object.entries({X:one,Y:one,Z:q,T:u}))word(expectedEnd,n,value);
  same(end.ring,expectedEnd);same(marks(end),['marker']);same(visible(end),[v,one,one,q,u]);
  same(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&w.before!==w.value
    &&!allowed.has(w.chip+':'+w.command)),[],'no undeclared changed tetra in the complete closing tail');
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.after,{...r.before,U:r.before.U,V:r.before.V.slice(0,2)+q,W:r.before.W.slice(0,2)+p,
    Q:r.before.Q.slice(0,2)+a,P7:r.before.P7.slice(0,2)+b,P8:r.before.P8.slice(0,2)+v});
  const mapping=Array.from({length:23},(_,i)=>i);
  for(const [dst,src] of [[0,17],[16,18],[17,0],[18,19],[19,20],[20,16]])mapping[dst]=src;
  const oracle=analyzeTrace({beforeEvent:r.traced.events.find(e=>e.ring),afterEvent:end,
    writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');
  const rows=repack.boundaryLosses(full);same(rows.filter(x=>x.missing.length),[]);
  if(full.options.verifyExit) {
    const done=checks.boundary(full,'done'),post=checks.boundary(full,'post/manual').command;
    same(full.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(full,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(full,'post/program').ring.X),zero);
    same(raw(done.ring.X),'000050000000');same(marks(done),['marker']);
    same(snapshotFromRing(done.ring).words,snapshotFromRing(end.ring).words);
    same(full.after, r.after);same(full.afterRegisters,r.afterRegisters);same(full.afterProgram,full.beforeProgram);
    same(full.traced.writes.filter(w=>w.command>=post&&w.before!==w.value&&
      ((w.nibble%3===0&&w.nibble<36)||(Object.hasOwn(full.before,w.slot)&&w.nibble%3===1)||
        [36,37,39,40].includes(w.nibble))),[],'manual and program tests leave bank/services unchanged');
  }
  return {prefix,boundaries:rows.length,lift:{...lift,...liftOutput},saveU,
    swap:{...swap,...swapOutput},saveQ,drops,mapping,cycles:oracle.data.cycles,
    all23BackInStoredWords:true,allExtraMarkersRemoved:true,noSpillOnlyInVisibleStack:true,
    upperP7P8Included:true,upperP9P10Held:true,workingExitTested:!!full.options.verifyExit,
    repeatabilityProved:false,numericDomainProved:false,fullK1:false};
}

function negativePhase(r) {
  same(r.options.closePhases,[2,0,0]);same(r.options.closeSteps,3);assert.ok(!r.options.verifyExit);
  const prefix=rotate.check(r,{beforeDropStage:'close/lift-u/phase'});
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  const u=r.before.U.slice(2),q=r.before.Q.slice(2),p=r.beforeRegisters[0];
  const at=checks.boundary(r,'close/swap-q'),end=checks.boundary(r,'done');
  same(visible(at).slice(1),[u,q,m,m]);
  const ee=r.traced.events.filter(e=>e.stage==='close/swap-q');
  same(ee.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E],['control',0x9E]]);
  const reads=ee.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw]),[['V',u],['X',p]]);
  const copy=ee.filter(e=>e.ip===0xE9);same(copy.length,1);repack.exactCopy(r,copy[0],'X1',u);
  const req=ee.filter(e=>e.ip===0xA3);same(req.length,1);same(req[0].slot,'T');
  const after=ringAt(r,req[0].command+1);same(raw(after.T),'14'+u[2]+m.slice(3));
  same(visible(end).slice(1),[p,p,m,'14'+u[2]+m.slice(3)]);
  same(repack.boundaryLosses(r).filter(e=>e.missing.length).map(e=>[e.stage,e.missing]),[['done',[q]]]);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  const live=[...snapshotFromRing(end.ring).words,...visible(end)];same(original.filter(x=>!live.includes(x)),[q]);
  return {prefix,rejectedPhase:0,acceptedAt:'control',wrongRequest:'T',lostOriginalQ:q,
    lostFromStoredAndVisibleWords:true,safeBlindRetry:false,notGeneralImpossibility:true};
}

if(require.main===module) {
  const negative=!!process.env.K1_STACK_CLOSE_NEGATIVE;
  const o={...probe.defaults,verifyExit:!negative,...JSON.parse(process.env.K1_STACK_CLOSE_OPTIONS||'{}'),
    ...(negative?{closeSteps:3,closePhases:[2,0,0]}:{})};
  if(process.env.K1_STACK_CLOSE_LARGE_V)o.values=['-1.2345678E-42','-7.654321E-23','-9.8765432E-3','-12345678'];
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS '+(negative?'rejected phase':'closed upper permutation')+':',
    JSON.stringify((negative?negativePhase:check)(r)));
  if(process.env.K1_STACK_CLOSE_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check,negativePhase};
