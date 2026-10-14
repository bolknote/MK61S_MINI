#!/usr/bin/env node
'use strict';
// Research candidate. Asymmetric pointer copies compensate both M1 bases.
// The default continuation is an experiment, NOT a proven safe return.
const upper=require('./probe_ms_upper_indirect.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function prepare(o={}) {
  const c=upper.prepare(o);
  for(const k of ['Сx','K','-','ВП','K','0'])c.press(k).runFrames(12);
  c.pressSequence(['X→П','2']).runFrames(8);
  for(let i=0;i<4;i++)c.pressSequence(['П→X','3']).runFrames(8);
  c.pressSequence(['Сx','В↑','В↑','В↑','+']);
  for(const [value,key] of [['8','6'],[o.dPointer??'1','Сx'],['9','7'],['2','В↑'],[o.eraser??'-1.2345678E-42','4'],
    ...(o.p1Pointer===undefined?[]:[[o.p1Pointer,'1']])]) {
    inputLiteral(c,value);c.pressSequence(['X→П',key]);
  }
  return aligned(c);
}
const defaultTail=[['K','П→X','В↑'],['K','П→X','Сx'],['П→X','4']];
const optionsFor=o=>({...o,afterKeys:o.afterKeys??defaultTail});
const finish=(c,o={},record=()=>{})=>upper.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>upper.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  const es=r.traced.events;
  return {options:r.options,before:r.before,after:r.after,regs:r.afterRegisters,
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    path:es.filter(e=>e.stage.startsWith('upper-after-')&&e.stage!=='upper-after-0'&&
      [0x9C,0xD6,0xD4,0x70,0xE7].includes(e.ip)).map(e=>[e.stage,e.ip.toString(16),e.slot,raw(e.r,0),e.nextIp.toString(16)]),
    stages:es.filter((e,i)=>e.ring&&(i===0||e.stage!==es[i-1].stage))
      .filter(e=>e.stage.startsWith('upper-after-')).map(e=>({stage:e.stage,
        ring:Object.fromEntries(['X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'].map(n=>[n,raw(e.ring[n])]))})),
    end:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,raw(es.findLast(e=>e.ring).ring[n])]))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief,optionsFor};
