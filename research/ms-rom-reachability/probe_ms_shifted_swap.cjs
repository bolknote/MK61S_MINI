#!/usr/bin/env node
'use strict';
// Structural source-offset experiments for the native IK1303 reader.
// No state injection: moving the false marker is done by zero P3 recalls.
const assert=require('node:assert/strict');
const {prepare}=require('./probe_ms_classic_v.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const raw=m=>Array.from({length:12},(_,i)=>m[34-3*i].toString(16).toUpperCase()).join('');

function finish(calc,{lifts=2,settleFrames=8,markerFrames=12,phaseOffset=0,
  postSwap=[],save=true,finalLifts=4,sourceKey=['↔']}={},record=()=>{}) {
  assert.ok([0,1,2,3].includes(lifts));assert.ok([0,1,2].includes(phaseOffset));
  calc.runFrames(phaseOffset);const stages=[];
  const actions=[['clear-before',['Сx','В↑','В↑','В↑','+'],settleFrames],
    ...['Сx','K','-','ВП','K','0'].map((k,i)=>['marker-'+i,[k],markerFrames]),
    ...Array.from({length:lifts},(_,i)=>['lift-'+i,['П→X','3'],settleFrames]),
    ['shifted-swap',sourceKey,settleFrames],
    ...postSwap.map((ks,i)=>['post-swap-'+i,ks,settleFrames]),
    ...(save?[['save',['X→П','9'],settleFrames]]:[]),
    ...Array.from({length:finalLifts},(_,i)=>['clear-marker-'+i,['П→X','3'],settleFrames]),
    ['clear-after',['Сx','В↑','В↑','В↑','+'],settleFrames]];
  for(const [label,ks,wait] of actions) {
    record(label);calc.pressSequence(ks).runFrames(wait);
    stages.push({label,display:calc.displayText()});
  }
  return stages;
}
function runPrepared(calc,options={}) {
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  assert.equal(beforeRegisters[3],'000000000000');let stage='',stages=[],seen=new Set();
  const traced=trace(calc,c=>{stages=finish(c,options,s=>{stage=s;});stage='done';c.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      otherChipsAt:()=>stage==='shifted-swap'||stage.startsWith('post-swap')||stage==='save',
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xA9,0xA2,0xA3,0xD4,0xD6].includes(e.ip)||
          [0x53,0xD4,0x3A,0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(calc);
  return {calc,options,stages,traced,before,after:fullMsPages(calc),beforeRegisters,
    afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc)};
}
function run(options={}) {return runPrepared(prepare(options),options);}
function brief(r) {
  const es=r.traced.events;
  return {options:r.options,before:r.before,after:r.after,p9:r.afterRegisters[9],
    programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    msWrites:r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value),
    stageStarts:es.filter(e=>e.ring&&es.find(x=>x.stage===e.stage)===e).map(e=>({stage:e.stage,
      stack:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,raw(e.ring[n])]))})),
    readers:es.filter(e=>e.stage==='shifted-swap'&&e.otherChips?.[4].ip===0x53).map(e=>({
      command:e.command,slot:e.otherChips[4].slot,word:raw(e.otherChips[4].m),
      fields:[e.otherChips[4].l,e.otherChips[4].s1,...[32,35,41].map(i=>e.otherChips[4].r[i])]}))
      .filter((x,i,a)=>!i||x.slot!==a[i-1].slot||x.word!==a[i-1].word||x.fields.join()!==a[i-1].fields.join()),
    c9:es.filter(e=>e.ip===0xC9).length};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,run,runPrepared,brief,raw};
