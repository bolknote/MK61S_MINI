#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const checks=require('./k1-lower-stack-cycle-check.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing,MS_SLOTS}=require('./k1-permutation-oracle.cjs');
function run(o={}) {
  o={...historical.defaults,...o,verifyExit:true};
  const c=capture.prepare(o),before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  aligned(c);let stage='',totalWrites=0,protectedWrites=0;const seen=new Set(),postChanges=[];
  const traced=trace(c,calc=>{checks.repeated(calc,o,s=>{stage=s;});stage='done';calc.runFrames(3);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:ip=>!seen.has(stage)||[0xC7,0xC8,0xC9].includes(ip),
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);return first;},
    onWrite:w=>{
      totalWrites++;
      const protectedField=w.nibble%3===2||[36,37,39,40].includes(w.nibble)||
        (w.nibble%3===0&&w.nibble<36&&w.slot!=='U')||
        (MS_SLOTS.includes(w.slot)&&!['U','V','W'].includes(w.slot)&&w.nibble%3===1);
      if(protectedField){
        protectedWrites++;
        if(stage==='post/program'&&w.nibble%3===2) {
          if(w.value!==w.before)postChanges.push(w);
        } else assert.equal(w.value,w.before,'streaming protected field '+JSON.stringify(w));
      }
    },
  });
  aligned(c);
  if(postChanges.length)console.log('DIAGNOSTIC post-program writes:',JSON.stringify(postChanges.slice(0,12)));
  assert.deepEqual(fullMsPages(c),before);assert.deepEqual(registers(c),beforeRegisters);
  assert.deepEqual(program(c),beforeProgram);
  const at=prefix=>{const e=traced.events.find(e=>e.stage.startsWith(prefix));assert.ok(e,prefix);return e;};
  let expected=[...beforeRegisters,...MS_SLOTS.map(n=>before[n].slice(2))];
  for(let i=0;i<4;i++) {
    const a=at('cycle'+i+'/'),b=at(i===3?'post/manual':'between-'+(i+1));
    assert.deepEqual(snapshotFromRing(a.ring).words,expected,'cycle '+i+' incoming 23 words');
    const next=expected.slice();next[0]=expected[17];next[15]=expected[0];next[16]=expected[15];next[17]=expected[16];
    assert.deepEqual(snapshotFromRing(b.ring).words,next,'cycle '+i+' outgoing 23 words');
    assert.deepEqual(Object.keys(b.ring).filter(n=>b.ring[n][22]===15),['marker']);expected=next;
  }
  assert.deepEqual(beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
  assert.equal(raw(at('post/zero').ring.X),'000050000000','manual two plus three');
  assert.equal(raw(at('post/program').ring.X),'000000000000','independent zero sentinel');
  assert.equal(raw(at('done').ring.X),'000050000000','saved program independently computes five');
  assert.ok(traced.events.filter(e=>e.stage!=='post/program').every(e=>![0xC7,0xC8,0xC9].includes(e.ip)));
  const state=JSON.parse(JSON.stringify(c));
  return {c,options:o,traced,state,summary:{cycles:4,all23Restored:true,
    perCyclePermutation:true,allMarkersRemovedEachTime:true,manualFive:true,zeroSentinel:true,
    savedProgramFive:true,totalWrites,protectedWrites,postProgramChangedWrites:postChanges.length}};
}
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_CYCLE_OPTIONS||'{}'));
  console.log('PASS four uninterrupted cycles:',JSON.stringify(r.summary));
  if(process.env.K1_CYCLE_UNOBSERVED)console.log('PASS full observer-free four-cycle state:',
    keyboard.compareUnobserved(r.state,r.options,checks.repeated));
}
module.exports={run};
