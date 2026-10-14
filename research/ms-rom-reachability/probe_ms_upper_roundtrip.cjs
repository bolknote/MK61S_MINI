#!/usr/bin/env node
'use strict';
// Read/restore only the upper half of Ms. Keep a=P1, b=P3, c=B;
// d is parked in lower Ms V, carried to Q by each remaining upper push,
// then recovered in P6. Lower Ms is explicitly cleared, NOT preserved.
// No program/data import, state injection, live getters or alignment calls.
const assert=require('node:assert/strict');
const reader=require('./probe_ms_upper_read4.cjs');
const zero=require('./probe_ms_zero_p0.cjs');
const two=require('./probe_ms_two_markers.cjs');
const push=require('./probe_ms_p9_push.cjs');
const shifted=require('./probe_ms_shifted_swap.cjs');
const {recoverV}=require('./probe_ms_read6_roundtrip.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');

function prepare(o={}) {
  const c=reader.prepare(o);
  if(o.initialP3!==undefined) {
    inputLiteral(c,o.initialP3);c.pressSequence(['X→П','3']).runFrames(8);aligned(c);
  }
  return c;
}
const under=(record,prefix)=>label=>record(prefix+'/'+label);
function pushOptions(o={}) {
  const result=zero.optionsFor({...o,phaseOffset:0,keepP8:false,legacyCopy:false,directSource:false});
  result.tailActions=result.tailActions.filter(a=>!['upper-prime','upper-swap'].includes(a[0]));
  return result;
}
function write(c,o,record) {
  zero.prepareScratch(c,o,record);two.finish(c,pushOptions(o),record);
}
function parkEighth(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8;
  record('save-b');c.pressSequence(['П→X','3','X→П','В↑']).runFrames(wait);
  record('zero-p3');inputLiteral(c,'0');c.pressSequence(['X→П','3']).runFrames(wait);
  record('d-to-p9');c.pressSequence(['П→X',',','X→П','9']).runFrames(wait);
  push.finish(c,o,under(record,'d-to-u'));
  record('zero-source');c.pressSequence(['П→X','0','X→П','9']).runFrames(wait);
  push.finish(c,o,under(record,'d-to-v'));
  record('restore-b');c.pressSequence(['П→X','В↑','X→П','3']).runFrames(wait);
}
function finalRead(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8;
  record('save-b');c.pressSequence(['П→X','3','X→П','В↑']).runFrames(wait);
  record('zero-p3');inputLiteral(c,'0');c.pressSequence(['X→П','3']).runFrames(wait);
  shifted.finish(c,{...o,lifts:3,save:false},under(record,'exchange-wq'));
  shifted.finish(c,{...o,lifts:2,postSwap:[['П→X','3'],['П→X','3'],['F',','],['F',','],['F',',']],save:true},under(record,'read-q'));
  record('d-to-p6');c.pressSequence(['П→X','9','X→П','6']).runFrames(wait);
  record('zero-source');c.pressSequence(['П→X','0','X→П','9']).runFrames(wait);
  for(let i=0;i<4;i++)push.finish(c,o,under(record,'clear-lower-'+i));
  record('restore-b');c.pressSequence(['П→X','В↑','X→П','3']).runFrames(wait);
  for(let i=0;i<4;i++){record('clear-visible-'+i);c.pressSequence(['П→X','0']).runFrames(wait);}
  record('clear-final');c.pressSequence(['Сx','В↑','В↑','В↑','+']).runFrames(wait);
}
function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0,keepP8:false,legacyCopy:false,directSource:false,finalRestore:false,legacyBridgeReturn:false};
  const wait=o.settleFrames??8;
  record('initial-zero-p3');inputLiteral(c,'0');c.pressSequence(['X→П','3']).runFrames(wait);
  reader.finish(c,{...local,clearInitialU:true,pairOnly:false,skipZeroU:false},under(record,'read-four'));
  record('zero-before-write');c.pressSequence(['П→X','3','X→П','9']).runFrames(wait);
  push.finish(c,local,under(record,'clean-entry-u'));
  record('b-to-p3');c.pressSequence(['П→X','6','X→П','3']).runFrames(wait);
  write(c,{...local,sourceIndex:o.reverseFirstTwo?11:10},under(record,'push-d'));
  write(c,{...local,sourceIndex:o.reverseFirstTwo?10:11},under(record,'push-c'));
  parkEighth(c,local,under(record,'park-d'));
  record('b-to-a');c.pressSequence(['П→X','3','X→П',',']).runFrames(wait);
  write(c,{...local,sourceIndex:10},under(record,'push-b'));
  if(!o.skipBridge)recoverV(c,local,under(record,'bridge-d'));
  record('a-to-a');c.pressSequence(['П→X','1','X→П',',']).runFrames(wait);
  write(c,{...local,sourceIndex:10},under(record,'push-a'));
  finalRead(c,local,under(record,'finish-d'));
  return c;
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  let stage='',seen=new Set();
  const short=new Set([0xAC,0xEE,0xDE,0x9C,0xC9,0xD4,0xD6,0xA2,0xA3,0xE5,0xE6,0xE8,0xA7,0xE7,0xA8,0xA9,0xA5,0x47]);
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||stage.includes('/upper-')||stage.endsWith('/shifted-swap')||stage.includes('/post-swap-')||short.has(ip),
      otherChipsAt:()=>stage.endsWith('/upper-swap')||stage.endsWith('/shifted-swap')||stage.includes('/post-swap-'),
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xA9,0xA5,0xD4,0xD6,0x47].includes(e.ip)||[0x3A,0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,before,after:fullMsPages(c),beforeRegisters,
    afterRegisters:registers(c),beforeProgram,afterProgram:program(c)};
}
const run=o=>runPrepared(prepare(o),o);
function brief(r) {
  const names=['U','V','W','Q','P7','P8','P9','P10'];
  const labels=['zero-before-write','b-to-p3','push-d/prepare-zero-p8','push-c/prepare-zero-p8',
    'park-d/save-b','b-to-a','bridge-d/save-q-backup','a-to-a','finish-d/save-b','finish-d/d-to-p6','done'];
  return {before:r.before,after:r.after,registers:r.afterRegisters,
    copies:[1,3,11,6].map((reg,i)=>({word:names[i+4],reg,expected:r.before[names[i+4]].slice(2),actual:r.afterRegisters[reg]})),
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    boundaries:labels.map(label=>{const e=r.traced.events.find(e=>e.stage===label&&e.ring);return e&&{label,
      ms:Object.fromEntries(names.map(n=>[n,two.raw(e.ring[n])]))};}),
    end:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,two.raw(r.traced.events.findLast(e=>e.ring).ring[n])]))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,pushOptions,write,parkEighth,finalRead,finish,runPrepared,run,brief};
