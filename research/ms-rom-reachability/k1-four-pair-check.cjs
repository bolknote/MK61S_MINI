#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const four=require('./k1-four-pair-exchange.cjs');
const tripleChecks=require('./k1-three-pair-check.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing,MS_SLOTS}=require('./k1-permutation-oracle.cjs');
const same=(a,b)=>assert.deepEqual(a,b),swap=(a,i,j)=>{[a[i],a[j]]=[a[j],a[i]];};
function apply(a,label) {
  if(label.startsWith('triple-'))for(let i=0;i<3;i++)swap(a,i,15+i);
  else if(label.startsWith('vq-'))swap(a,16,18);
  else swap(a,1,3);
}
const mapping=Array.from({length:23},(_,i)=>i);
for(const label of four.labels)apply(mapping,label);
const wanted=Array.from({length:23},(_,i)=>i);for(let i=0;i<4;i++)swap(wanted,i,15+i);
same(mapping,wanted);
function operation(c,o={},record=()=>{}) {
  (o.twice?four.twice:four.finish)(c,o,record);
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.press('Сx').runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
function run(o={},observed=true) {
  o={...historical.defaults,...o};const c=tripleChecks.prepare(o);
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);aligned(c);
  const original=[...beforeRegisters,...MS_SLOTS.map(n=>before[n].slice(2))];assert.equal(new Set(original).size,23);
  let stage='',writes=0,postProgramWrites=0;const seen=new Set();
  const body=calc=>{operation(calc,o,s=>{stage=s;});stage='done';calc.runFrames(3);};
  const t=observed?trace(c,body,{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:ip=>!seen.has(stage)||[0xC7,0xC8,0xC9].includes(ip),
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);return first;},
    onWrite:w=>{
      writes++;
      if(stage==='post/program'&&w.nibble%3===2){if(w.value!==w.before)postProgramWrites++;return;}
      if(w.nibble%3===2||[36,37,39,40].includes(w.nibble)||
        (w.nibble%3===0&&w.nibble<36&&!['U','V','W','Q'].includes(w.slot))||
        (MS_SLOTS.slice(4).includes(w.slot)&&w.nibble%3===1))same(w.value,w.before);
    }}):(body(c),null);
  aligned(c);const after=fullMsPages(c),afterRegisters=registers(c),afterProgram=program(c);
  same([...afterRegisters,...MS_SLOTS.map(n=>after[n].slice(2))],o.twice?original:mapping.map(i=>original[i]));
  same(afterProgram,beforeProgram);
  let boundaries=0;
  if(t) {
    const at=p=>{const e=t.events.find(e=>e.stage.startsWith(p)&&e.ring);assert.ok(e,p);return e;};
    const check=(e,words)=>{same(snapshotFromRing(e.ring).words,words);
      same(Object.keys(e.ring).filter(n=>e.ring[n][22]===15),['marker']);boundaries++;};
    const words=original.slice();
    for(let round=0;round<(o.twice?2:1);round++) {
      const prefix=o.twice?(round?'second/':'first/'):'';
      for(const label of four.labels){check(at(prefix+label+'/'),words);apply(words,label);}
      check(at(o.twice&&!round?'second/':o.verifyExit?'post/manual':'done'),words);
    }
    assert.ok(t.events.filter(e=>e.stage!=='post/program').every(e=>![0xC7,0xC8,0xC9].includes(e.ip)));
    if(o.verifyExit) {
      same(beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
      same(raw(at('post/zero').ring.X),'000050000000');
      same(raw(at('post/program').ring.X),'000000000000');
      same(raw(at('done').ring.X),'000050000000');
    }
  }
  if(o.verifyExit)same(keyboard.stack(c).X,'000050000000');
  const state=JSON.parse(JSON.stringify(c));
  return {state,summary:{phase:o.phaseOffset??0,exchanges:o.twice?2:1,boundaries,
    all23Preserved:true,other11OrdinaryHeld:true,upperFourMsHeld:true,programHeld:true,
    workingExit:!!o.verifyExit,writes,postProgramWrites,fullK1:false,
    sha256:createHash('sha256').update(JSON.stringify(c)).digest('hex')}};
}
function surface() {
  const ds=Array(18).fill('1,'); // 3*4 triple readers + 2*3 Q-swap readers.
  const a=control.record(ds,{},four.finish);
  same(a,control.record(ds,{bank:['unread'],incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},four.finish));
  same(a.seen,ds);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  same([keys,frames],[1212,9421]);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempt:1,
    algebra:'P0/U, P1/V, P2/W, P3/Q; all other stored words held'};
}
if(require.main===module) {
  console.log('PASS algebra and surface:',JSON.stringify(surface()));
  const o={bank:['-1.2345678E-42','12345678','9.8765432E73','-6.5432109E65'],
    values:['1E-99','-9.8765432E99','-12345678','-1.2E-42'],
    ...JSON.parse(process.env.K1_FOUR_OPTIONS||'{}')};
  const r=run(o,!process.env.K1_FOUR_COMPACT);console.log('PASS four-pair exchange:',JSON.stringify(r.summary));
  if(process.env.K1_FOUR_UNOBSERVED){const plain=run(o,false);same(plain.state,r.state);
    console.log('PASS all serialized fields without observer:',plain.summary.sha256);}
}
module.exports={mapping,apply,operation,run,surface};
