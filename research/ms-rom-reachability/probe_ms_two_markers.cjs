#!/usr/bin/env node
'use strict';
// Experimental keyboard-only second-marker placement. This is a probe,
// not a safe user protocol: lower Ms words are deliberately displaced.
const assert=require('node:assert/strict');
const base=require('./probe_ms_classic_v.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const clear=['Сx','В↑','В↑','В↑','+'];
const marker=['Сx','K','-','ВП','K','0'];
const raw=(m,lane=1,count=12)=>Array.from({length:count},(_,i)=>m[lane+3*(count-1-i)].toString(16).toUpperCase()).join('');

const prepare=(options={})=>base.prepare({values:['111','222','333','444'],...options});
function finish(calc,{phaseOffset=0,settleFrames=8,markerFrames=12,shifts=1,
  reads=false,readSteps=[0,1,2],zeroKey='8',zeroRegister='3',keepP8=false,payloadKey='9',payloadCopies=[],cleanup=false,tailActions=[]}={},record=()=>{}) {
  assert.ok([0,1,2].includes(phaseOffset));
  assert.ok(Number.isInteger(shifts)&&shifts>=0&&shifts<=4);
  assert.ok(['8','3'].includes(zeroKey));
  assert.ok(['0','3'].includes(zeroRegister));
  assert.ok(['9',','].includes(payloadKey));
  assert.ok(Array.isArray(payloadCopies)&&payloadCopies.every(k=>['1','6','В↑'].includes(k)));
  calc.runFrames(phaseOffset);
  const actions=[['prepare-zero-p8',['П→X',zeroRegister,...(keepP8?[]:['X→П','8'])],settleFrames],
    ['clear-before',clear,settleFrames],
    ...marker.map((k,i)=>['payload-marker-'+i,[k],markerFrames]),
    ['store-payload-'+(payloadKey==='9'?'p9':'a'),['X→П',payloadKey],settleFrames],
    ...payloadCopies.map(key=>['copy-payload-'+key,['X→П',key],settleFrames]),
    ...Array.from({length:4},(_,i)=>['remove-payload-'+i,['П→X',zeroRegister],settleFrames]),
    ['clear-payload',clear,settleFrames],
    ...marker.map((k,i)=>['visible-marker-'+i,[k],markerFrames]),
    ['lift-visible-y',['П→X',zeroRegister],settleFrames],
    ['plant-u',['П→X',payloadKey],settleFrames],
    ...Array.from({length:shifts},(_,i)=>[
      ['shift-'+i,['П→X',zeroKey],settleFrames],
      ...(reads&&readSteps.includes(i)?[['read-'+i,['X→П',String(i)],settleFrames]]:[])]).flat(),
    ...tailActions.map(([label,keys,frames])=>[label,keys,frames??settleFrames]),
    ...(cleanup?[
      ...Array.from({length:4},(_,i)=>['cleanup-'+i,['П→X',zeroRegister],settleFrames]),
      ['clear-after',clear,settleFrames]]:[])];
  const stages=[];
  for(const [label,keys,frames] of actions) {
    record(label);calc.pressSequence(keys).runFrames(frames);
    stages.push({label,display:calc.displayText()});
  }
  return stages;
}
function runPrepared(calc,options={}) {
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  assert.equal(beforeRegisters[Number(options.zeroRegister??3)],'000000000000');
  let stage='',stages=[],seen=new Set();
  const traced=trace(calc,c=>{
    stages=finish(c,options,label=>{stage=label;});stage='done';c.runFrames(3);
  },{extraIps:options.traceAll?Array.from({length:256},(_,i)=>i):
    [0x9B,0x9C,0xD4,0xD6,0xAA,0xE5,0xE6,0xE8,0xE7,0xA7,0xA8,0xA9,0xAD,0xA4],
    fullState:true,allWrites:true,
    otherChipsAt:options.traceSecondary?()=>stage.startsWith('upper-'):undefined,
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
      return first||[0xE7,0xA9,0xD4,0xEE].includes(e.ip)||(options.traceFormatterExit&&e.ip===0x47)||
        [0x53,0x4E,0x2A,0x3A,0xD4,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(calc);
  return {calc,options,stages,traced,before,after:fullMsPages(calc),beforeRegisters,
    afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc)};
}
const run=(options={})=>runPrepared(prepare(options),options);
function brief(r) {
  const es=r.traced.events;
  return {options:r.options,before:r.before,after:r.after,
    registers:r.afterRegisters,programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    stages:r.stages,stageRings:es.filter((e,i)=>e.ring&&(i===0||e.stage!==es[i-1].stage)).map(e=>({stage:e.stage,
      words:Object.fromEntries(['X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'].map(n=>[n,raw(e.ring[n])]))})),
    transfers:es.filter(e=>['plant-u','done'].includes(e.stage)||e.stage.startsWith('shift-')||e.stage.startsWith('read-'))
      .filter(e=>[0xD6,0xEE,0xE7,0xA8,0xA9,0xD4].includes(e.ip))
      .map(e=>({stage:e.stage,ip:e.ip.toString(16),slot:e.slot,raw:e.raw,a:raw(e.r,0)})),
    falseControls:[...new Set(es.filter(e=>e.ip===0x9C&&['U','V','W','Q'].includes(e.slot))
      .map(e=>JSON.stringify({stage:e.stage,slot:e.slot,raw:e.raw,next:e.nextIp.toString(16)})))].map(JSON.parse)};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief,raw};
