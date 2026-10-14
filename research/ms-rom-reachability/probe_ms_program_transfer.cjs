#!/usr/bin/env node
'use strict';
// A separate user-program experiment, NOT a program-preserving standalone ABI.
// Known data and the reader program are installed through keys only.
const assert=require('node:assert/strict');
const {prepare:prepareData}=require('./probe_ms_classic_v.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');

function prepare(options={}) {
  const calc=prepareData(options),before=fullMsPages(calc);
  const clear=['Сx','В↑','В↑','В↑','+'];
  let prefix=['Сx','K','Сx','K','8'];
  if(options.marker==='register') {
    calc.pressSequence(clear).runFrames(8);
    for(const key of ['Сx','K','-','ВП','K','0'])calc.press(key).runFrames(12);
    calc.pressSequence(['X→П','8']).runFrames(8);
    for(let i=0;i<4;i++)calc.pressSequence(['П→X','3']).runFrames(8);
    calc.pressSequence(clear).runFrames(8);aligned(calc);
    assert.equal(registers(calc)[8],'0000F0000000');
    assert.deepEqual(fullMsPages(calc),before,'preparing the marker constant must preserve Ms');
    prefix=['П→X','8'];
  }
  const lifts=options.lifts??3;
  const command=options.command??['X→П','1'];
  const keys=[...clear,...prefix,...Array.from({length:lifts},()=>['П→X','3']).flat(),
    ...command,...Array.from({length:4-lifts},()=>['П→X','3']).flat(),...clear,'С/П'];
  calc.pressSequence(['В/О','F','ВП',...keys,'F','/-/','В/О']);aligned(calc);
  assert.deepEqual(fullMsPages(calc),before,'installing the test program must preserve Ms');
  return calc;
}
function run(options={}) {
  const calc=prepare(options),before=fullMsPages(calc),beforeProgram=program(calc),beforeRegisters=registers(calc);
  const traced=trace(calc,c=>c.runFrames(options.phaseOffset??0).pressSequence(['В/О','С/П']).runFrames(options.frames??40),
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      otherChipsAt:e=>[0xA0,0xA2,0xA3,0xAA,0xE7,0xD4,0xD6].includes(e.ip),
      ringAt:e=>[0xAA,0xE7,0xEE,0xA3].includes(e.ip)});
  aligned(calc);return {calc,options,before,after:fullMsPages(calc),beforeProgram,afterProgram:program(calc),
    beforeRegisters,afterRegisters:registers(calc),traced};
}
function brief(r) {
  return {options:r.options,pc:r.calc.programCounter(),display:r.calc.displayText(),
    code:r.beforeProgram.slice(0,24).map(x=>x.toString(16).toUpperCase()),before:r.before,after:r.after,
    regs:r.afterRegisters,programUnchanged:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    msWrites:r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value).slice(0,20),
    stores:r.traced.events.filter(e=>e.ip===0xD4).map(e=>({pc:e.pc,slot:e.slot,command:e.command})),
    reads:r.traced.events.filter(e=>e.ip===0xEE).slice(0,35).map(e=>({pc:e.pc,slot:e.slot,raw:e.raw,command:e.command}))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,run,brief};
