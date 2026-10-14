#!/usr/bin/env node
'use strict';
// Exact passive evidence for a continuous G; C^2; B composition.
// No keyboard controller reads these diagnostic snapshots.
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const probe=require('./k1-adapted-third-entry.cjs');
const previous=require('./k1-repeat-entry-adapter-audit.cjs');
const previousProbe=require('./k1-repeat-entry-adapter.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const {mapping,lowerMappings}=require('./k1-adapted-third-entry-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const surface=require('./k1-x1-retry-reader-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const markers=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const rotationIps='6E 5E 50 52 53 4F 24 26 28 D3 37 37 37 37 37 37 27 D4 D4 D4 D4 D4 C4 2C 3B 2B 60 37 37 37 37 27 61 3A 3A 3A 2A 39';
const ySwapIps='6E 5E 50 52 53 4F 41 43 4D 60 37 37 27 61 4E 2A 39';
const swapIps='6E 5E 50 52 53 4F 41 43 4D 60 37 37 37 37 37 37 27 61 4E 2A 39';

function publicSurface(o={}) {
  o={...probe.defaults,...o};const displays=Array.from({length:12},(_,i)=>(i%9+1)+',');
  const a=surface.record(displays,o,probe.finish);
  same(a,surface.record(displays,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,displays);same(a.result,undefined);
  for(const [verifyExit,wanted] of [[false,'459f76dfcad594e57baa0a5920120c917d79766a5f98124d58a43a320056fc19'],
    [true,'557f15bef9b1cb50254d2916bb768d5d61d0aaa2df62eac44caeae81d0b051f7']]) {
    const old=surface.record(['1,','2,','3,','4,','5,','6,','7,'],{...previousProbe.closedDefaults,verifyExit},previousProbe.finish);
    same(createHash('sha256').update(JSON.stringify(old)).digest('hex'),wanted,'old G actions unchanged');
  }
  const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicKeysWaitsAndDisplayOnly:true,assumedFirstSuccessfulReaderAttempts:12,oldGActionFingerprintsHeld:true};
}

function check(full) {
  const r=full.options.verifyExit?prefixView(full,'post/manual'):full;
  same(r.options.lowerRounds,2);same(r.options.thirdPhase,0);
  same(r.options.adapterPhase,probe.defaults.adapterPhase);
  same(r.options.adapterActions,probe.defaults.adapterActions);
  same(r.options.exitActions,probe.defaults.exitActions);same(r.options.lowerPush,true);
  const f=prefixView(r,'lower/0/lower-load',{verifyExit:false});
  f.traced.events=f.traced.events.map(e=>({...e,stage:e.stage.replace(/^previous\//,'')}));
  const old=previous.check(f);
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const rows=repack.boundaryLosses(full);same(rows.filter(e=>e.missing.length),[]);
  const initial=r.traced.events.find(e=>e.ring),original=snapshotFromRing(initial.ring);
  same(new Set(original.words).size,23);
  const lowerBounds=[checks.boundary(r,'lower/0/lower-load'),checks.boundary(r,'lower/1/lower-load'),
    r.traced.events.find(e=>e.stage.startsWith('third/')&&e.ring)];
  for(const [i,e] of lowerBounds.entries()) {
    assert.ok(e);same(snapshotFromRing(e.ring).words,lowerMappings[i].map(j=>original.words[j]));
    same(markers(e),['marker']);
  }
  const lowerPushes=[];
  for(let i=0;i<2;i++) {
    const push=checks.exactPush(r,'lower/'+i+'/lower/push',['T','U','V','W']);
    const before=ringAt(r,push.command),incoming=lowerMappings[i].map(j=>original.words[j]);
    same(['T','U','V','W'].map(n=>raw(before[n])),[incoming[0],incoming[15],incoming[16],incoming[17]]);
    same(push.displaced,incoming[17]);lowerPushes.push(push);
    const ww=r.traced.writes.filter(w=>w.command>=lowerBounds[i].command&&w.command<lowerBounds[i+1].command);
    // Q and all four upper words are protected throughout each lower bridge,
    // not merely restored at its endpoint.
    same(ww.filter(w=>['Q','P7','P8','P9','P10'].includes(w.slot)&&w.nibble%3===1&&w.before!==w.value),[]);
  }
  const [u,v,w,q,b]=['U','V','W','Q','P8'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const entry=checks.boundary(r,'third/adapter/0');
  // This entry creates a neutral marker; the preceding B used 9990FFFFFFF0.
  same(visible(entry),[q,b,u,p,'0000FFFFFFF0']);
  const operations=[],add=(s,next,spec)=>operations.push(previous.operation(r,'third/'+s,'third/'+next,spec));
  add('adapter/0','second/entry/tail-0',{gates:[['control',0x9E],['control',0x9E]],
    source:'W',value:b,copy:'X1',request:'U',opcode:0x25,consumer:'T',acks:['U','U'],path:rotationIps,
    pairs:[['W','Q'],['Q','P7'],['P7','P8'],['P8','W']],lateSource:'Q',lateValue:q,lateTarget:'X',zeros:0,markers:['marker','T','U']});
  add('second/entry/tail-0','second/entry/tail-1',{gates:[['U',0x9E],['U',0x9E]],
    source:'X',value:q,copy:'V',request:'control',opcode:0x25,consumer:'marker',acks:['control','control'],path:rotationIps,
    pairs:[['X','Y'],['Y','Z'],['Z','T'],['T','X']],lateSource:'X',lateValue:q,lateTarget:'V',zeros:0,markers:['marker','Z','U']});
  add('second/entry/tail-1','exit/0',{gates:[['T',0x9E],['T',0x9E]],
    source:'X',value:u,copy:'U',request:'control',opcode:0x25,consumer:'marker',acks:['control','control'],path:rotationIps,
    pairs:[['X','Y'],['Y','Z'],['Z','T'],['T','X']],lateSource:'X',lateValue:u,lateTarget:'U',zeros:0,small:true,markers:['marker','Y']});
  add('exit/0','exit/1',{gates:[['control',0x9E],['control',0x9E]],
    source:'X',value:p,copy:'X1',request:'Z',opcode:0x14,consumer:'Y',acks:['control'],path:ySwapIps,
    pairs:[['X','V'],['Y','X']],lateSource:'X',lateValue:q,lateTarget:'X',zeros:0,markers:['marker'],lateReadAfterOutput:true});
  add('exit/1','exit/push/blind-duplicate',{gates:[['control',0x9E],['control',0x9D],['control',0x9E]],
    source:'X',value:q,copy:'X1',request:'control',opcode:0x14,consumer:'marker',acks:['control'],path:swapIps,
    pairs:[['X','Y'],['Y','X']],lateSource:'X',lateValue:p,lateTarget:'X',zeros:5,small:true,markers:['marker'],lateReadAfterOutput:true});
  const duplicate=checks.boundary(r,'third/exit/push/blind-duplicate'),duplicated=checks.boundary(r,'third/exit/push/push-marker-0');
  same(markers(duplicate),['marker']);same(visible(duplicate),[q,p,q,'14'+p[2]+q.slice(3),u]);
  const des=r.traced.events.filter(e=>e.stage==='third/exit/push/blind-duplicate');
  const pushes=des.filter(e=>e.ip===0xE7&&e.nextIp===0xA8).map(first=>checks.exactPush({...r,
    traced:{...r.traced,events:r.traced.events.filter(e=>e.command>=first.command)}},'third/exit/push/blind-duplicate',['X','Y','Z','T']));
  same(pushes.length,3);same(pushes.map(x=>x.displaced),[u,'14'+p[2]+q.slice(3),q]);
  same(visible(duplicated),[q,p,p,p,p]);
  const push=checks.exactPush(r,'third/exit/push/push',['T','U','V','W']);same(push.displaced,q);
  const before=ringAt(r,push.command);same(['T','U','V','W'].map(n=>raw(before[n])),[p,u,q,q]);
  const allowedMs=new Set([push.command+1,push.command+2,push.command+3]);
  same(r.traced.writes.filter(x=>x.command>=duplicate.command&&x.before!==x.value&&
    ((x.nibble%3===0&&x.nibble<36)||(Object.hasOwn(r.before,x.slot)&&x.nibble%3===1&&
      !(x.chip===3&&allowedMs.has(x.command)&&['U','V','W'].includes(x.slot)&&x.nibble<37)))),[]);
  const end=checks.boundary(r,'done');
  same(snapshotFromRing(end.ring).words,mapping.map(i=>original.words[i]));same(markers(end),['marker']);
  const oracle=analyzeTrace({beforeEvent:initial,afterEvent:end,writes:r.traced.writes,expectedMapping:mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');
  if(full.options.verifyExit) {
    const done=checks.boundary(full,'done'),post=checks.boundary(full,'post/manual').command;
    same(full.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(full,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(full,'post/program').ring.X),'000000000000');
    same(raw(done.ring.X),'000050000000');same(markers(done),['marker']);
    same(snapshotFromRing(done.ring).words,snapshotFromRing(end.ring).words);same(full.afterProgram,full.beforeProgram);
    same(full.traced.writes.filter(w=>w.command>=post&&w.before!==w.value&&
      ((w.nibble%3===0&&w.nibble<36)||(Object.hasOwn(full.before,w.slot)&&w.nibble%3===1)||[36,37,39,40].includes(w.nibble))),[]);
  }
  return {previousCompositionReaudited:old.all23BackInStoredWords,boundaries:rows.length,
    lowerPushes,operations,duplicates:pushes,push,all23BackInStoredWords:true,
    allExtraMarkersRemoved:true,allFourUpperWordsRestored:true,other14OrdinaryAndLastTwoMsHeld:true,
    cycles:oracle.data.cycles,workingExitTested:!!full.options.verifyExit,
    uninterruptedThirdEntry:true,unboundedRepetitionProved:false,wholeNumericDomainProved:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,verifyExit:true,...JSON.parse(process.env.K1_THIRD_ENTRY_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(publicSurface(o)));
  const r=probe.traced(o);console.log('PASS exact third entry:',JSON.stringify(check(r)));
  if(process.env.K1_THIRD_ENTRY_UNOBSERVED)console.log('PASS complete state without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check,publicSurface};
