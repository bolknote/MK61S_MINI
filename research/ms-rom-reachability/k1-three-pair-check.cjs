#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const exchange=require('./k1-three-pair-exchange.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing,MS_SLOTS}=require('./k1-permutation-oracle.cjs');
const same=(a,b)=>assert.deepEqual(a,b);
const swap=(a,i,j)=>{[a[i],a[j]]=[a[j],a[i]];};
const rotate=a=>{const w=a[17];a[17]=a[16];a[16]=a[15];a[15]=a[3];a[3]=w;};
const mapping=Array.from({length:23},(_,i)=>i);
for(let i=0;i<4;i++){rotate(mapping);if(i<3)swap(mapping,3,[2,1,0][i]);}
const wanted=Array.from({length:23},(_,i)=>i);
for(let i=0;i<3;i++)swap(wanted,i,15+i);
same(mapping,wanted); // Algebra checked independently of numeric emulator data.
function prepare(o) {
  const c=capture.prepare(o),before=fullMsPages(c);
  if(o.bank)for(const [i,v] of o.bank.entries()){inputLiteral(c,v);c.pressSequence(['X→П',String(i)]).runFrames(8);}
  aligned(c);same(fullMsPages(c),before);return c;
}
function operation(c,o={},record=()=>{}) {
  (o.twice?exchange.twice:exchange.finish)(c,o,record);
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.press('Сx').runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
function run(o={},observed=true,negativeWide=false) {
  o={...historical.defaults,...o};const c=prepare(o);
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);aligned(c);
  let stage='',writes=0,postProgramWrites=0;const seen=new Set();
  const body=calc=>{operation(calc,o,s=>{stage=s;});stage='done';calc.runFrames(3);};
  const traced=observed?trace(c,body,{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:ip=>!seen.has(stage)||[0xC7,0xC8,0xC9].includes(ip),
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);return first;},
    onWrite:w=>{
      writes++;
      if(stage==='post/program'&&w.nibble%3===2){if(w.value!==w.before)postProgramWrites++;return;}
      if(w.nibble%3===2||[36,37,39,40].includes(w.nibble)||
        (w.nibble%3===0&&w.nibble<36&&!['U','V','W','Q'].includes(w.slot))||
        (MS_SLOTS.includes(w.slot)&&!['U','V','W'].includes(w.slot)&&w.nibble%3===1))
        assert.equal(w.value,w.before,'protected tetra '+JSON.stringify(w));
    },
  }):(body(c),null);
  aligned(c);const after=fullMsPages(c),afterRegisters=registers(c),afterProgram=program(c);
  const originals=[...beforeRegisters,...MS_SLOTS.map(n=>before[n].slice(2))];assert.equal(new Set(originals).size,23);
  const target=(o.twice?originals.slice(): mapping.map(i=>originals[i]));
  if(negativeWide) {
    same(o.bank,['-1.2345678E-42','12345678','9.8765432E73']);
    assert.ok(!o.twice&&!o.verifyExit);
    for(const i of [0,3,16])target[i]=originals[2];
  }
  same([...afterRegisters,...MS_SLOTS.map(n=>after[n].slice(2))],target);same(afterProgram,beforeProgram);
  if(o.verifyExit)assert.equal(keyboard.stack(c).X,'000050000000');
  let firstDivergence=null;
  if(traced) {
    const at=p=>{const e=traced.events.find(e=>e.stage.startsWith(p)&&e.ring);assert.ok(e,p);return e;};
    const clean=(e,words)=>{
      const actual=snapshotFromRing(e.ring).words;
      if(negativeWide) {
        if(!firstDivergence&&JSON.stringify(actual)!==JSON.stringify(words))firstDivergence={stage:e.stage,
          differences:actual.flatMap((v,i)=>v===words[i]?[]:[{index:i,wanted:words[i],actual:v}])};
      } else same(actual,words);
      same(Object.keys(e.ring).filter(n=>e.ring[n][22]===15),['marker']);
    };
    let words=originals.slice();
    for(let round=0;round<(o.twice?2:1);round++) {
      const prefix=o.twice?(round?'second/':'first/'):'';
      for(let i=0;i<4;i++) {
        clean(at(prefix+'pair-cycle'+i+'/'),words);rotate(words);
        if(i<3) {
          clean(at(prefix+'pair-swap'+i+'/0'),words);swap(words,3,[2,1,0][i]);
          clean(at(prefix+'pair-between-'+(i+1)),words);
        } else clean(at(o.twice&&!round?'pair-inverse-gap':o.verifyExit?'post/manual':'done'),words);
      }
    }
    assert.ok(traced.events.filter(e=>e.stage!=='post/program').every(e=>![0xC7,0xC8,0xC9].includes(e.ip)));
    if(o.verifyExit) {
      same(beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
      assert.equal(raw(at('post/zero').ring.X),'000050000000');
      assert.equal(raw(at('post/program').ring.X),'000000000000');
      assert.equal(raw(at('done').ring.X),'000050000000');
    }
  }
  const state=JSON.parse(JSON.stringify(c));
  if(negativeWide) {
    same(originals.flatMap((v,i)=>target.includes(v)?[]:[i]),[1,3,15]);
    if(observed)assert.ok(firstDivergence);
  }
  return {state,options:o,summary:{observed,exchanges:o.twice?2:1,all23Preserved:!negativeWide,
    p3Restored:afterRegisters[3]===beforeRegisters[3],otherElevenRegistersHeld:true,otherFiveMsHeld:true,
    programHeld:true,workingExit:!!o.verifyExit,writes,postProgramWrites,
    ...(negativeWide?{expectedFailure:true,missingStoredOrigins:['P1','P3','Ms U'],firstDivergence}:{}),
    sha256:createHash('sha256').update(JSON.stringify(c)).digest('hex')}};
}
function surface(o={}) {
  const record=o.reader==='x1-retry'?
    (o,fn)=>require('./k1-x1-retry-reader-check.cjs').record(['1,','1,','1,','1,'],o,fn).actions:keyboard.record;
  const actions=record(o,exchange.finish),keys=actions.filter(a=>a[0]==='key').length;
  same(actions,record({...o,bank:['not read'],incoming:'not read',values:['not read']},exchange.finish));
  const frames=keys*2+actions.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0);
  const expected=o.reader==='x1-retry'?[279,2173]:o.reader==='zero-nop'?[195,1645]:[175,1825];expected[1]+=o.phaseOffset??0;
  same([keys,frames],expected);
  return {keys,frames,noHiddenReads:true,publicDisplay:o.reader==='x1-retry',
    ...(o.reader==='x1-retry'?{assumedSuccessfulAttempt:1}:{}),algebra:'P0/U, P1/V, P2/W; P3 held'};
}
if(require.main===module) {
  const o=JSON.parse(process.env.K1_THREE_OPTIONS||'{}');
  console.log('PASS algebra and keyboard surface:',JSON.stringify(surface(o)));
  if(process.env.K1_THREE_NEGATIVE_WIDE) {
    console.log('PASS rejected wide-input composition:',JSON.stringify(run({
      bank:['-1.2345678E-42','12345678','9.8765432E73'],
    },true,true).summary));process.exit(0);
  }
  const r=run(o,!process.env.K1_THREE_COMPACT);
  console.log('PASS native three-pair exchange:',JSON.stringify(r.summary));
  if(process.env.K1_THREE_UNOBSERVED){const plain=run(o,false);same(plain.state,r.state);
    console.log('PASS all serialized fields without observer:',plain.summary.sha256);}
}
module.exports={mapping,prepare,operation,run,surface};
