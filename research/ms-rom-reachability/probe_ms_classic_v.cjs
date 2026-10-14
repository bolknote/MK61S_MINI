#!/usr/bin/env node
'use strict';
// A standalone, keyboard-only V reader. It does not install a reader program,
// prepare 600/700 words, or reserve P8. Only P3=0 is required on entry.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');

function prepare({values=['111','222','333','-1.2345678E-42'],stress=false}={}) {
  const calc=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw new Error('Forbidden state setter: '+name);};
  // Separate, known native fixture writer; NOT part of the reading operation.
  if(values!==null) preparePayload(values,calc);
  // A nonempty user-program fixture, so preservation is not tested only on 00.
  calc.pressSequence(['В/О','F','ВП','2','В↑','3','+','С/П','K','0',
    'F','/-/','В/О']);
  assert.deepEqual(program(calc).slice(0,6),[2,0x0E,3,0x10,0x50,0x54]);
  const registerKeys=[...'0123456789',',','/-/','ВП','Сx','В↑'];
  if(stress) for(let i=0;i<15;i++) if(i!==3)
    calc.inputNumber(String(101+i),{clear:true}).pressSequence(['X→П',registerKeys[i]]);
  return aligned(calc);
}

function finish(calc,{settleFrames=8,markerFrames=12,phaseOffset=0,lifts=2,destination=2,stores=1}={},record=()=>{}) {
  assert.ok([1,2,3].includes(lifts));
  assert.ok(Number.isInteger(settleFrames)&&settleFrames>=1);
  assert.ok(Number.isInteger(markerFrames)&&markerFrames>=1);
  assert.ok([0,1,2].includes(phaseOffset));
  assert.ok(Number.isInteger(destination)&&destination>=0&&destination<=9&&destination!==3);
  assert.ok(Number.isInteger(stores)&&stores>=1&&stores<=3);
  calc.runFrames(phaseOffset);
  const stages=[];
  const actions=[['clear-before',['Сx','В↑','В↑','В↑','+'],settleFrames],
    ...['Сx','K','-','ВП','K','0'].map((key,i)=>['make-marker-'+i,[key],markerFrames]),
    ...Array.from({length:lifts},(_,i)=>['lift-marker-'+(i+1),['П→X','3'],settleFrames]),
    ...Array.from({length:stores},(_,i)=>[i?'save-direct-repeat-'+i:'save-v-direct',
      ['X→П',String(destination)],settleFrames]),
    ...Array.from({length:4-lifts},(_,i)=>['remove-marker-'+(i+1),['П→X','3'],settleFrames]),
    ['clear-after',['Сx','В↑','В↑','В↑','+'],settleFrames]];
  for(const [label,keys,frames] of actions) {
    record(label);calc.pressSequence(keys).runFrames(frames);
    stages.push({label,display:calc.displayText()});
  }
  return stages;
}

function runPrepared(calc,options={}) {
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  assert.equal(beforeRegisters[3],'000000000000','the reader requires an explicit zero P3');
  let stage='',stages=[],seen=new Set();
  const record=label=>{stage=label;};
  const traced=trace(calc,c=>{
    stages=finish(c,options,record);record('done');c.runFrames(3);
  },{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
      return first||[0xEE,0xE7,0xD4,0xD6,0xAD,0xA8,0xA9,0xAC].includes(e.ip);}});
  aligned(calc);
  return {calc,options,stages,traced,before,after:fullMsPages(calc),
    beforeRegisters,afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc)};
}

function run(options={}) { return runPrepared(prepare(options),options); }

if(require.main===module) {
  const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});
  console.log(JSON.stringify({options:r.options,stages:r.stages,before:r.before,after:r.after,
    p2:r.afterRegisters[2],msUnchanged:JSON.stringify(r.before)===JSON.stringify(r.after),
    programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)},null,2));
}
module.exports={prepare,finish,run,runPrepared};
