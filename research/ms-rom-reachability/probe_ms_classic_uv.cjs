#!/usr/bin/env node
'use strict';
// Compose the two native readers directly: NO phase alignment, state read,
// snapshot import, or reset between U and V.
const assert=require('node:assert/strict');
const u=require('./probe_ms_classic_u.cjs');
const v=require('./probe_ms_classic_v.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');

function finish(calc,options={},record=()=>{}) {
  const order=options.order??['u','v'];
  assert.ok(JSON.stringify(order)==='["u","v"]'||JSON.stringify(order)==='["v","u"]');
  calc.runFrames(options.phaseOffset??0);const stages=[];
  for(const name of order) {
    const child=(name==='u'?u:v).finish(calc,{...options,phaseOffset:0},label=>record(name+'/'+label));
    stages.push(...child.map(s=>({...s,label:name+'/'+s.label})));
  }
  return stages;
}

function runPrepared(calc,options={}) {
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  assert.equal(beforeRegisters[3],'000000000000');
  let stage='',stages=[],seen=new Set();
  const record=label=>{stage=label;};
  const traced=trace(calc,c=>{stages=finish(c,options,record);record('done');c.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      otherChipsAt:()=>stage==='u/swap-read-u',
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xD4,0xD6,0xA8,0xA9,0xAD,0xAC].includes(e.ip);}});
  aligned(calc);
  return {calc,options,stages,traced,before,after:fullMsPages(calc),
    beforeRegisters,afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc)};
}
function run(options={}) {return runPrepared(v.prepare(options),options);}
if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify({p9:r.afterRegisters[9],p2:r.afterRegisters[2],
    before:r.before,after:r.after,programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)},null,2));
}
module.exports={run,runPrepared,finish};
