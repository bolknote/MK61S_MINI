#!/usr/bin/env node
'use strict';
// Full passive write audit of the phase-matched repeat's first lost word.
const assert=require('node:assert/strict');
const probe=require('./k1-stack-close-repeat.cjs');
const close=require('./k1-zero-rotate-stack-close-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const surface=require('./k1-x1-retry-reader-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const word=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});
const live=ring=>[...snapshotFromRing(ring).words,...['X1','X','Y','Z','T'].map(n=>raw(ring[n]))];
const extraStages=['entry/clone-swap-0','entry/tail-0','entry/tail-1','entry/after-0'];

function publicSurface(o={}) {
  o={...probe.defaults,...o};const ds=['1,','2,','3,','4,','5,','6,','7,','8,'];
  const a=surface.record(ds,o,probe.finish);
  same(a,surface.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);same(a.result,{failure:null});
  const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    onlyKeysWaitsAndPublicDisplays:true,assumedFirstSuccessfulReaderAttempts:true};
}

function firstRoundView(r) {
  // record(end) alone does not advance native time and is superseded by
  // the next action label. Use its actual pre-wait event, without adding
  // a fake wait, copying state back, or inventing an execution boundary.
  const first=prefixView(r,'repeat/1/wait');
  return {...first,traced:{...first.traced,events:first.traced.events.map(e=>
    ({...e,stage:e.stage.replace(/^repeat\/0\//,'')}))}};
}

function formatterPath(zeros) {
  const seq='EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE D9'.split(' ').map(x=>parseInt(x,16));
  seq.push(...Array.from({length:zeros+1},()=>[0xF3,0xF7,0xF1]).flat(),
    ...Array.from({length:8-zeros},()=>[0xF4,0xF6]).flat(),0xF4,0xEA,0xEC);
  same(seq.length,39+zeros);seq.push(0x40,0x41,0x42,0x46);
  while(!['marker','Z','U'].includes(slots[(3+seq.length)%15]))seq.push(0xE5);
  seq.push(0xE5,0xE6,0xE8,0xE7);
  return seq;
}

function rotation(r,round,source,target,zeros) {
  const stage='repeat/'+round+'/entry/tail-0';
  const start=checks.boundary(r,stage),end=checks.boundary(r,'repeat/'+round+'/entry/tail-1');
  const es=r.traced.events.filter(e=>e.stage===stage),allowed=new Set();
  const permit=(chip,c)=>allowed.add(chip+':'+c);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['U',0x9E],['U',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE);same(reads.map(e=>[e.slot,e.raw,e.nextIp]),
    [['X',source,0xA1],['X',source,0xE3]]);
  const copies=es.filter(e=>e.ip===0xE9);same(copies.length,1);
  repack.exactCopy(r,copies[0],'V',source);permit(3,copies[0].command);
  const requests=es.filter(e=>e.ip===0xA3);same(requests.length,1);const req=requests[0];same(req.slot,'control');
  const request=ringAt(r,req.command),values=[parseInt(source[2],16),5,2];
  [28,31,34].forEach((n,j)=>{request.control[n]=values[j];});
  same(ringAt(r,req.command+1),request,'only three request tetras');
  same(r.traced.writes.filter(w=>w.command===req.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
    [28,31,34].map((n,j)=>[3,'control',n,values[j]]));permit(3,req.command);
  const out=r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command&&w.chip===4);
  same(out.filter(w=>w.ip===0x27).map(w=>[w.slot,w.nibble,w.before,w.value]),
    [['control',31,5,15],['control',31,15,15]]);
  const output=repack.visibleRotation(r,stage),expectedOutput=ringAt(r,output),old=structuredClone(expectedOutput);
  ['X','Y','Z','T'].forEach((n,j)=>word(expectedOutput,n,raw(old[['Y','Z','T','X'][j]])));
  same(ringAt(r,output+4),expectedOutput);
  same(r.traced.writes.filter(w=>w.command>=output&&w.command<output+4).map(w=>[w.chip,w.slot,w.nibble]),
    ['X','Y','Z','T'].flatMap(n=>Array.from({length:12},(_,j)=>[4,n,1+3*j])));
  const ips='6E 5E 50 52 53 4F 24 26 28 D3 37 37 37 37 37 37 27 D4 D4 D4 D4 D4 C4 2C 3B 2B 60 37 37 37 37 27 61 3A 3A 3A 2A 39'.split(' ').map(x=>parseInt(x,16));
  const route=es.filter(e=>e.command>=req.command&&e.command<req.command+ips.length);
  same(route.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),ips.map((ip,i)=>[ip,slots[i%15]]));
  const secondary=route[0].otherChips[4];same([secondary.r[29],secondary.st[36],secondary.st[39],secondary.st[37],secondary.st[40]],
    [0,10,3,10,3]);
  out.forEach(w=>permit(4,w.command));
  const lates=es.filter(e=>e.ip===0xE7);same(lates.length,1);const late=lates[0];
  repack.exactCopy(r,late,target,source);permit(3,late.command);
  const path=formatterPath(zeros),native=es.filter(e=>e.command>=reads[1].command&&e.command<reads[1].command+path.length);
  same(native.map(e=>[e.ip,e.slot]),path.map((ip,i)=>[ip,slots[(3+i)%15]]),'complete native formatter route');
  same(late.command,reads[1].command+path.length-1);
  assert.ok(reads[1].command<output&&output+4<=late.command,'old X read before rotation; formatter writes after it');
  same(Object.keys(expectedOutput).filter(n=>expectedOutput[n][22]===15).sort(),['U','Z','marker']);
  const expected=structuredClone(start.ring);
  word(expected,'V',source);word(expected,'control','2F'+source[2]+raw(start.ring.control).slice(3));
  for(const [dst,src] of [['X','Y'],['Y','Z'],['Z','T'],['T','X']])word(expected,dst,raw(start.ring[src]));
  word(expected,target,source);same(end.ring,expected,'exact complete rotation endpoint, all 630 tetras');
  same(r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command&&w.before!==w.value
    &&!allowed.has(w.chip+':'+w.command)),[],'no undeclared changed tetra');
  return {stage,source,copy:copies[0].command,request:req.command,lateRead:reads[1].command,
    secondaryOutput:output,lateWrite:late.command,lateTarget:target,formatterClass:zeros};
}

function check(r) {
  same(r.options.betweenFrames,1);same(r.options.rounds,2);same(r.failure,null);
  assert.ok(!r.options.longGuardBeforeRepeatRotate&&!r.options.verifyExit);
  const first=close.check(firstRoundView(r));
  const phase=e=>(84+42*e.command)%252;
  same(phase(checks.boundary(r,'repeat/0/entry/load-original-p0')),84);
  same(phase(checks.boundary(r,'repeat/1/wait')),0);
  same(phase(checks.boundary(r,'repeat/1/entry/load-original-p0')),84);
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  const q=r.before.Q.slice(2),a=r.before.P7.slice(2);
  same(raw(checks.boundary(r,'repeat/1/wait').ring.Q),a,'first call places old upper a in Q');
  const passing=rotation(r,0,q,'V',0),failing=rotation(r,1,a,'X',7);
  const beforeLate=ringAt(r,failing.lateWrite),afterLate=ringAt(r,failing.lateWrite+1);
  same(original.filter(x=>!live(beforeLate).includes(x)),[],'all 23 still live immediately before destructive E7');
  same(snapshotFromRing(beforeLate).words.filter(x=>x===q),[]);
  same(['X1','X','Y','Z','T'].filter(n=>raw(beforeLate[n])===q),['X'],'q has one remaining visible copy');
  same(original.filter(x=>!live(afterLate).includes(x)),[q],'E7 alone removes that copy');
  const rows=repack.boundaryLosses(r),firstLoss=rows.findIndex(x=>x.missing.length);
  same(rows[firstLoss-1].stage,'repeat/1/entry/tail-0');
  same([rows[firstLoss].stage,rows[firstLoss].missing],['repeat/1/entry/tail-1',[q]]);
  return {firstCall:first,passing,failing,firstMissingOriginal:q,originalPlace:'Ms.Q',
    all23LiveImmediatelyBeforeLateWrite:true,originalMissingImmediatelyAfterLateWrite:true,
    ringPhaseMatchedByOneFixedFrame:true,onlyKeysAndWaitsBetweenCalls:true,
    lossIsNotOnlyStartPhaseMismatch:true,noClaimAboutOtherInternalChipCopies:true,
    wholeProtocolDomainClosedUnderItsPermutation:false,fullK1:false,notGeneralImpossibility:true};
}

if(require.main===module) {
  const o={...probe.defaults,betweenFrames:1,...JSON.parse(process.env.K1_STACK_REPEAT_AUDIT_OPTIONS||'{}')};
  console.log('PASS public surface:',JSON.stringify(publicSurface(o)));
  const r=probe.traced(o,extraStages);console.log('PASS exact repeat obstruction:',JSON.stringify(check(r)));
  if(process.env.K1_STACK_REPEAT_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check,rotation,firstRoundView,publicSurface,extraStages};
