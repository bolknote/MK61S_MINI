#!/usr/bin/env node
'use strict';
// Candidate idempotent U preparation. With a marker in Z and accepted
// false control in T, the displaced primary path should read X then
// E5(Z)/E6(T)/E9(U). Other entry phases may instead read V and clear X1.
// Whether BOTH routes preserve the still-live W/Q is a native obligation.
const assert=require('node:assert/strict');
const base=require('./probe_ms_lower_exchange.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const clear=['Сx','В↑','В↑','В↑','+'];
function prepare(o={}) {
  return base.prepare({values:['11','22','33','-1E-99'],...o,bank:o.bank??['201','202','203','0']});
}
function finish(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8,markerWait=o.markerFrames??12,rounds=o.rounds??1;
  assert.ok(Number.isInteger(wait)&&wait>=1);assert.ok(Number.isInteger(markerWait)&&markerWait>=1);
  assert.ok([0,1,2].includes(o.phaseOffset??0));assert.ok(Number.isInteger(rounds)&&rounds>=1&&rounds<=6);
  c.runFrames(o.phaseOffset??0);
  const act=(stage,keys,frames=wait)=>{record(stage);c.pressSequence(keys).runFrames(frames);};
  act('clear-before',clear);
  for(const [i,key] of ['Сx','K','-','ВП','K','0'].entries())act('marker-'+i,[key],markerWait);
  act('store-marker-d',['X→П','Сx']);
  for(let i=0;i<4;i++)act('remove-marker-'+i,['П→X','3']);
  act('clear-marker-source',clear);
  for(let i=0;i<rounds;i++) {
    const prefix='guard-'+i+'/';
    record(prefix+'control-number');inputLiteral(c,'-1E-99');c.runFrames(wait);
    act(prefix+'load-marker',['П→X','Сx']);
    act(prefix+'lift-0',['П→X','3']);act(prefix+'lift-1',['П→X','3']);
    act(prefix+'shifted-swap',['↔']);
    for(let n=0;n<4;n++)act(prefix+'cleanup-'+n,['П→X','3']);
    act(prefix+'clear',clear);
    // Default control literal has seven keys: a round is 54+10*wait
    // frames. Cover all three frame phases even when wait is divisible
    // by three. This schedule depends on options, never observed state.
    if(i+1<rounds&&o.phaseSweep!==false&&wait%3===0){record(prefix+'phase-sweep');c.runFrames(1);}
  }
  return c;
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  assert.equal(beforeRegisters[3],'000000000000');let stage='',seen=new Set();
  const short=new Set([0x9C,0xEE,0xA1,0xE5,0xE6,0xE7,0xE9,0xA2,0xA3,0xD4,0xD6,0xA8,0xA9,0x47,0xC9]);
  const secondary=()=>stage.endsWith('/shifted-swap')||stage.includes('/cleanup-');
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||secondary()||short.has(ip),otherChipsAt:secondary,
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xE9,0xA2,0xA3,0xD4,0xD6,0xA9,0x47].includes(e.ip)||
          [0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,before,beforeRegisters,beforeProgram,
    after:fullMsPages(c),afterRegisters:registers(c),afterProgram:program(c)};
}
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  const es=r.traced.events;
  return {options:r.options,before:r.before,after:r.after,registers:r.afterRegisters,
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    entries:es.filter(e=>e.stage.endsWith('/shifted-swap')&&[0x9C,0xEE,0xE9,0xA3].includes(e.ip))
      .map(e=>({stage:e.stage,command:e.command,ip:e.ip.toString(16),slot:e.slot,next:e.nextIp.toString(16),word:e.raw})),
    start:es.filter(e=>e.stage.endsWith('/shifted-swap')).filter((e,i,a)=>!i||e.stage!==a[i-1].stage)
      .map(e=>({stage:e.stage,stack:['X','Y','Z','T'].map(n=>raw(e.ring[n]))})),
    changedMs:[...new Set(r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value).map(w=>w.slot))]};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief};
