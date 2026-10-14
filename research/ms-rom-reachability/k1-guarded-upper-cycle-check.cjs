#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const upper=require('./k1-guarded-upper-cycle.cjs');
const wideUpper=require('./k1-guarded-upper-wide-cycle.cjs');
const sixCheck=require('./k1-six-word-cycle-check.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing,MS_SLOTS}=require('./k1-permutation-oracle.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=(a,b)=>assert.deepEqual(a,b);
function rotate(words,slots) {
  const old=slots.map(i=>words[i]);slots.forEach((i,j)=>{words[i]=old[(j+slots.length-1)%slots.length];});
}
function apply(words,label,wide=false) {
  if(label==='six') {
    rotate(words,wide?[0,20,19,18,15]:[0,20,19,18,17,15]);
    if(wide)[words[16],words[17]]=[words[17],words[16]];
  }
  else if(label==='vq')[words[16],words[18]]=[words[18],words[16]];
  else rotate(words,[0,15,16,17]);
}
const mapping=Array.from({length:23},(_,i)=>i);
for(const s of upper.labels)apply(mapping,s);
const wanted=Array.from({length:23},(_,i)=>i);rotate(wanted,[0,20,19,17,15]);same(mapping,wanted);
const wideMapping=Array.from({length:23},(_,i)=>i);
for(const s of wideUpper.labels)apply(wideMapping,s,true);
const wideWanted=Array.from({length:23},(_,i)=>i);rotate(wideWanted,[0,20,19,15]);
[wideWanted[16],wideWanted[17]]=[wideWanted[17],wideWanted[16]];same(wideMapping,wideWanted);
function operation(c,o={},record=()=>{}) {
  // This candidate is phase-conditional. Its one-frame entry offset is a
  // part of EVERY invocation, not a one-time adjustment for the entire run.
  for(let i=0;i<(o.rounds??1);i++)(o.variant==='wide'?wideUpper:upper).finish(c,o,s=>record('round-'+i+'/'+s));
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.press('Сx').runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
function run(o={},observed=true) {
  o={...sixCheck.defaults,...o};const c=cap.prepare(o);
  const wide=o.variant==='wide',labels=wide?wideUpper.labels:upper.labels;
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);aligned(c);
  const original=[...beforeRegisters,...MS_SLOTS.map(n=>before[n].slice(2))];
  assert.equal(new Set(original).size,23);assert.ok(!original.includes('000000000000'));
  let stage='',writes=0;const seen=new Set();
  const body=calc=>{operation(calc,o,s=>{stage=s;});stage='done';calc.runFrames(3);};
  const t=observed?trace(c,body,{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:ip=>!seen.has(stage)||[0xC7,0xC8,0xC9].includes(ip),
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);return first;},
    onWrite:w=>{
      writes++;
      if(stage==='post/program'&&w.nibble%3===2)return;
      if(w.nibble%3===2||[36,37,39,40].includes(w.nibble)||
        (w.nibble%3===0&&w.nibble<36&&w.slot!=='U')||
        (['P9','P10'].includes(w.slot)&&w.nibble%3===1))
        assert.equal(w.value,w.before,'protected write '+JSON.stringify({stage,...w}));
    }}):(body(c),null);
  aligned(c);const after=fullMsPages(c),afterRegisters=registers(c),afterProgram=program(c);
  const expected=original.slice();for(let i=0;i<(o.rounds??1);i++) {
    rotate(expected,wide?[0,20,19,15]:[0,20,19,17,15]);
    if(wide)[expected[16],expected[17]]=[expected[17],expected[16]];
  }
  same([...afterRegisters,...MS_SLOTS.map(n=>after[n].slice(2))],expected);same(afterProgram,beforeProgram);
  if(o.verifyExit)same(keyboard.stack(c).X,'000050000000');
  let boundaries=0;
  if(t) {
    const at=p=>{const e=t.events.find(e=>e.stage.startsWith(p)&&e.ring);assert.ok(e,p);return e;};
    const clean=(e,words)=>{
      same(snapshotFromRing(e.ring).words,words);
      same(Object.keys(e.ring).filter(n=>e.ring[n][22]===15),['marker']);boundaries++;
    };
    const words=original.slice();
    for(let i=0;i<(o.rounds??1);i++)for(const label of labels) {
      clean(at('round-'+i+'/'+label+'/'),words);apply(words,label,wide);
    }
    clean(at(o.verifyExit?'post/manual':'done'),words);
    for(const e of t.events)if(e.ring) {
      const live=[...snapshotFromRing(e.ring).words,...['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]))];
      for(const x of original)assert.ok(live.includes(x),'lost '+x+' at '+e.stage);
    }
    assert.ok(t.events.filter(e=>e.stage!=='post/program').every(e=>![0xC7,0xC8,0xC9].includes(e.ip)));
    if(o.verifyExit) {
      same(beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
      same(raw(at('post/zero').ring.X),'000050000000');
      same(raw(at('post/program').ring.X),'000000000000');
      same(raw(at('done').ring.X),'000050000000');
    }
  }
  const state=JSON.parse(JSON.stringify(c));
  return {state,options:o,summary:{phase:o.phaseOffset,rounds:o.rounds??1,macroBoundaries:boundaries,
    scratchRetryAlignment:wide&&o.alignScratchRetries!==false,
    observed,cycles:wide?[['P0','Ms.P8','Ms.P7','Ms.U'],['Ms.V','Ms.W']]:[['P0','Ms.P8','Ms.P7','Ms.W','Ms.U']],qGuardRestored:true,
    all23StoredAtExit:true,all23RetainedAtEveryBoundary:!!t,upperLast2Held:true,
    programAndOther14OrdinaryHeld:true,workingExit:!!o.verifyExit,writes,fullK1:false,
    sha256:createHash('sha256').update(JSON.stringify(c)).digest('hex')}};
}
function surface(o={}) {
  const operation=o.variant==='wide'?wideUpper.finish:upper.finish;
  const ds=Array(11).fill('1,'),a=control.record(ds,{},operation);
  same(a,control.record(ds,{incoming:'unread',values:['unread'],fullUpper:['unread'],p3:'unread'},operation));
  same(a.seen,ds);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  const frames=keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  return {keys,frames,publicDisplayOnly:true,assumedSuccessfulAttempts:1};
}
function rejectedWideRepeat() {
  const o={variant:'wide',rounds:4,verifyExit:true,phaseOffset:1,alignScratchRetries:false,incoming:'-6.5432109E65',
    values:['-1.2345678E-42','-7.654321E-23','-9.8765432E99','-12345678'],
    fullUpper:['1.2345678E42','-1E-99','-7.654321E23','8.7654321E-17']};
  let violation;
  assert.throws(()=>run(o),e=>{
    const m=e.message.match(/^protected write (\{[^\n]+\})/);if(!m)return false;
    violation=JSON.parse(m[1]);
    same(violation,{stage:'round-3/six/restore-w-rotate-0',slot:'P9',nibble:1,before:0,
      chip:4,ip:0x2A,tick:1,command:8570875,value:8});
    return true;
  },'the rejected composition must reproduce its precise protected-word failure');
  return {expectedFailure:true,violation,repeatableWideCycle:false,fullK1:false};
}
if(require.main===module) {
  if(process.env.K1_GUARDED_EXPECT_WIDE_FAILURE) {
    console.log('PASS rejected wide repetition:',JSON.stringify(rejectedWideRepeat()));process.exit(0);
  }
  const o=JSON.parse(process.env.K1_GUARDED_OPTIONS||'{}');
  console.log('PASS algebra and keyboard surface:',JSON.stringify(surface(o)));
  const r=run(o,!process.env.K1_GUARDED_COMPACT);
  console.log('PASS guarded upper cycle:',JSON.stringify(r.summary));
  if(process.env.K1_GUARDED_UNOBSERVED) {
    const plain=run(o,false);same(plain.state,r.state);
    console.log('PASS all serialized fields without observer:',plain.summary.sha256);
  }
}
module.exports={rotate,apply,mapping,wideMapping,operation,run,surface,rejectedWideRepeat};
