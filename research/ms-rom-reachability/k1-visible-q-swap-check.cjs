#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const qswap=require('./k1-visible-q-swap.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing,MS_SLOTS}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b)=>assert.deepEqual(a,b),zero='000000000000';
const logical='9990FFFFFFF0',classic='0000F0000000';
function localRead(r,prefix,incoming,ordinary) {
  const start=checks.boundary(r,prefix+'attempt-0/read-prep-0');
  const original=snapshotFromRing(start.ring).words;
  same(raw(start.ring.X),incoming);
  const w=raw(start.ring.W),p=ordinary[0];let attempts=0;
  for(let i=0;i<3;i++) {
    const s=prefix+'attempt-'+i+'/';
    if(!r.traced.events.some(e=>e.stage===s+'read-store'))break;
    attempts++;
    const before=checks.boundary(r,s+'read-store');
    same(['X','Y','Z','T'].map(n=>raw(before.ring[n])),[zero,incoming,p,logical]);
    const read=r.traced.events.find(e=>e.stage===s+'read-store'&&e.ip===0xEE);assert.ok(read);
    assert.ok(['W','X'].includes(read.slot),'no unexplained source');
    same(read.raw,read.slot==='W'?w:zero);
    const ready=checks.boundary(r,s+'read-return-0');
    same(['X','Y','Z','T'].map(n=>raw(ready.ring[n])),[read.raw,zero,incoming,p]);
    const push=checks.exactPush(r,s+'read-clean',['X','Y','Z','T']);same(push.displaced,logical);
    const next=r.traced.events.find(e=>e.stage===prefix+'read-retry-'+(i+1)+'/0'&&e.ring)
      ??checks.boundary(r,prefix+'push-prep-0');
    same(snapshotFromRing(next.ring).words,original,'all stored words restored after read attempt');
    same(['X','Y','Z','T'].map(n=>raw(next.ring[n])),[read.raw,zero,incoming,p]);
  }
  same(raw(checks.boundary(r,prefix+'push-prep-0').ring.X),w);
  return attempts;
}
function check(r) {
  checks.protectedFields(r,[0],['U','V','W','Q']);
  same(r.afterRegisters,r.beforeRegisters);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>r.before[n].slice(2));
  same(r.after,{...r.before,V:r.before.V.slice(0,2)+q,Q:r.before.Q.slice(0,2)+v});
  const first=r.traced.events.find(e=>e.ring),end=checks.boundary(r,'done');
  const original=snapshotFromRing(first.ring).words;assert.equal(new Set(original).size,23);
  const final=original.slice();[final[16],final[18]]=[final[18],final[16]];
  same(snapshotFromRing(end.ring).words,final);
  same(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[zero,zero,zero,zero]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15),['marker']);
  const at=s=>checks.boundary(r,s);
  const lower=e=>['U','V','W','Q'].map(n=>raw(e.ring[n]));
  same(lower(at('q-duplicate')),[zero,u,v,q]);same(raw(at('q-duplicate').ring.X),w);
  same(['X','Y','Z','T'].map(n=>raw(at('q-swap').ring[n])),[zero,w,w,logical]);
  same(lower(at('q-swap')),[zero,u,v,q]);
  const h=raw(at('q-clean-marker').ring.U);
  same(lower(at('q-clean-marker')),[h,u,q,v]);assert.match(h,/^1F[0-9A-F]000000000$/);
  same(lower(at('move-hole-to-v/attempt-0/read-prep-0')),[h,u,q,v]);
  same(lower(at('move-hole-to-w/attempt-0/read-prep-0')),[w,h,u,v]);
  same(lower(at('discard-hole/blind-duplicate')),[q,w,h,v]);
  const attempts=[localRead(r,'park/',zero,r.beforeRegisters),
    localRead(r,'move-hole-to-v/',w,r.beforeRegisters),
    localRead(r,'move-hole-to-w/',q,r.beforeRegisters)];
  const pushes=[];
  for(const [prefix,incoming,returned] of [['park/',zero,w],['move-hole-to-v/',w,q],
    ['move-hole-to-w/',q,u],['discard-hole/',u,null]]) {
    const pre=at(prefix+'push');
    same(raw(pre.ring.X),classic);same(raw(pre.ring.T),incoming);
    const push=checks.exactPush(r,prefix+'push',['T','U','V','W']);
    same(push.displaced,returned??h);pushes.push(push.command);
  }
  const pair=r.traced.writes.filter(x=>x.command>=at('q-swap').command&&x.command<at('q-clean-marker').command&&
    x.chip===4&&[0x4E,0x2A].includes(x.ip));
  same(pair.map(x=>[x.ip,x.slot,x.nibble]),[[0x4E,'W'],[0x2A,'Q']]
    .flatMap(([ip,n])=>Array.from({length:12},(_,i)=>[ip,n,1+3*i])));
  const expected=ringAt(r,pair[0].command),old=structuredClone(expected);
  for(let j=0;j<12;j++){expected.W[1+3*j]=old.Q[1+3*j];expected.Q[1+3*j]=old.W[1+3*j];}
  same(ringAt(r,pair.at(-1).command+1),expected,'exact temporary W/Q exchange among all 630 tetras');
  // Every operation boundary retains all 23 originals, including the
  // temporarily displaced W in the visible stack rather than stored banks.
  const seen=new Set();let boundaries=0;
  for(const e of r.traced.events)if(e.ring&&!seen.has(e.stage)) {
    seen.add(e.stage);boundaries++;
    const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
    for(const word of original)assert.ok(live.includes(word),'lost origin at '+e.stage+': '+word);
  }
  return {phase:r.options.phaseOffset??0,swap:'V/Q',attempts,pushes,boundaries,
    all23RetainedAtEveryBoundary:true,allOrdinaryRestored:true,upperMsAndProgramHeld:true,fullK1:false};
}
function operation(c,o={},record=()=>{}) {
  qswap.finish(c,o,s=>record('first/'+s));
  if(o.twice)qswap.finish(c,{...o,phaseOffset:0},s=>record('second/'+s));
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.press('Сx').runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
function runCompact(o={},observed=true) {
  o={...historical.defaults,...o};const c=capture.prepare(o);
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);aligned(c);
  const original=[...beforeRegisters,...MS_SLOTS.map(n=>before[n].slice(2))];assert.equal(new Set(original).size,23);
  let stage='',writes=0;const seen=new Set();
  const body=calc=>{operation(calc,o,s=>{stage=s;});stage='done';calc.runFrames(3);};
  const t=observed?trace(c,body,{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:()=>!seen.has(stage),ringAt:e=>{e.stage=stage;seen.add(stage);return true;},
    onWrite:w=>{writes++;if(stage==='post/program'&&w.nibble%3===2)return;
      if(w.nibble%3===2||[36,37,39,40].includes(w.nibble)||
        (w.nibble%3===0&&w.nibble<36&&w.slot!=='U')||
        (MS_SLOTS.slice(4).includes(w.slot)&&w.nibble%3===1))same(w.value,w.before);}}):(body(c),null);
  aligned(c);const after=fullMsPages(c),afterRegisters=registers(c),afterProgram=program(c);
  const want=original.slice();if(!o.twice)[want[16],want[18]]=[want[18],want[16]];
  same([...afterRegisters,...MS_SLOTS.map(n=>after[n].slice(2))],want);same(afterProgram,beforeProgram);
  if(t) {
    const boundary=t.events.find(e=>e.stage.startsWith(o.twice?'second/':o.verifyExit?'post/manual':'done'));
    assert.ok(boundary);const one=original.slice();[one[16],one[18]]=[one[18],one[16]];
    same(snapshotFromRing(boundary.ring).words,one,'first exchange before inverse');
    const extra=Object.keys(boundary.ring).filter(n=>boundary.ring[n][22]===15);same(extra,['marker']);
    if(o.verifyExit)for(const [name,value] of [['post/zero','000050000000'],['post/program',zero],['done','000050000000']]) {
      const e=t.events.find(e=>e.stage===name);assert.ok(e);same(raw(e.ring.X),value);
    }
  }
  if(o.verifyExit)same(keyboard.stack(c).X,'000050000000');
  const state=JSON.parse(JSON.stringify(c));
  return {state,summary:{phase:o.phaseOffset??0,twice:!!o.twice,workingExit:!!o.verifyExit,writes,
    all23Held:true,sha256:createHash('sha256').update(JSON.stringify(c)).digest('hex')}};
}
function surface() {
  const a=control.record(['1,','1,','1,'],{},qswap.finish);
  same(a,control.record(['1,','1,','1,'],{incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},qswap.finish));
  const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedAttempts:[1,1,1]};
}
if(require.main===module) {
  console.log('PASS surface:',JSON.stringify(surface()));
  const o={incoming:'-6.5432109E65',values:['811','12345678','-9.8765432E99','-1E-99'],
    ...JSON.parse(process.env.K1_VQ_OPTIONS||'{}')};
  if(process.env.K1_VQ_COMPACT) {
    const r=runCompact(o);console.log('PASS repeatable V/Q:',JSON.stringify(r.summary));
    if(process.env.K1_VQ_UNOBSERVED){const p=runCompact(o,false);same(p.state,r.state);console.log('PASS full observer-free:',p.summary.sha256);}
  } else {
    const r=qswap.run(o);console.log('PASS exact V/Q:',JSON.stringify(check(r)));
    if(process.env.K1_VQ_UNOBSERVED)console.log('PASS full observer-free:',
      keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,qswap.finish));
  }
}
module.exports={localRead,check,operation,runCompact,surface};
