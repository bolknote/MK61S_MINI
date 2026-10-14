#!/usr/bin/env node
'use strict';
// Candidate lower exchange using the secondary W reader after U/V backup.
// The default Q path is the previous W/Q bridge and retains its entry caveat.
// qRoute='rotate' reproduces a rejected idea: Y/Z-marked R aligns its buffer
// to the true marker and writes buffered words into the visible stack,
// NOT the four Ms words. Its C/B sources may still come from lower Ms.
const assert=require('node:assert/strict');
const old=require('./probe_ms_lower_exchange.cjs');
const u=require('./probe_ms_classic_u.cjs');
const v=require('./probe_ms_classic_v.cjs');
const shifted=require('./probe_ms_shifted_swap.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {readQ}=require('./probe_ms_read8_roundtrip.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const under=(record,prefix)=>label=>record(prefix+'/'+label);
const prepare=old.prepare,move=old.move,brief=old.brief;
function readW(c,o={},record=()=>{}) {
  shifted.finish(c,{...o,lifts:2,sourceKey:['↔'],postSwap:
    [['П→X','3'],['П→X','3'],['F',','],['F',','],['F',',']],save:true},record);
}
function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0},wait=o.settleFrames??8;
  move(c,'3','В↑',local,record,'save-original-p3');
  record('zero-p3');inputLiteral(c,'0');c.pressSequence(['X→П','3']).runFrames(wait);
  u.finish(c,local,under(record,'read-u'));move(c,'9',',',local,record,'keep-u-in-a');
  v.finish(c,{...local,destination:9},under(record,'read-v'));move(c,'9','/-/',local,record,'keep-v-in-b');
  readW(c,local,under(record,'read-w'));move(c,'9','ВП',local,record,'keep-w-in-c');
  if(o.guardU)require('./probe_ms_u_guard.cjs').finish(c,{...local,rounds:o.guardRounds??3},under(record,'prepare-q'));
  if(o.qRoute==='rotate') {
    shifted.finish(c,{...local,lifts:o.rotationLifts??1,sourceKey:o.pairInstead?['↔']:['F',','],save:false},under(record,'rotate-lower'));
    readW(c,local,under(record,'read-q'));
  } else {
    assert.ok(o.qRoute===undefined||o.qRoute==='wq');readQ(c,local,under(record,'read-last'));
  }
  move(c,'9','Сx',local,record,'keep-q-in-d');
  for(const source of ['В↑','2','1','0']) {
    move(c,source,'9',local,record,'source-'+source);
    push.finish(c,local,under(record,'write-'+source));
  }
  for(const [from,to] of [[',','0'],['/-/','1'],['ВП','2'],['Сx','3']])
    move(c,from,to,local,record,'output-'+to);
  record('clear-final');c.pressSequence(['Сx','В↑','В↑','В↑','+']).runFrames(wait);return c;
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  let stage='',seen=new Set();
  const short=new Set([0xAC,0xEE,0xDE,0x9C,0xC9,0xD4,0xD6,0xA1,0xA2,0xA3,0xE5,0xE6,0xE8,0xA7,0xE7,0xE9,0xA8,0xA9,0xA5,0x47]);
  const secondary=()=>stage==='read-u/swap-read-u'||stage==='read-u/save-u'||stage.endsWith('/shifted-swap')||stage.includes('/post-swap-');
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||secondary()||short.has(ip),otherChipsAt:secondary,
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xE9,0xA2,0xA3,0xA9,0xA5,0xD4,0xD6,0x47].includes(e.ip)||
          [0x53,0xD4,0x4E,0x2A,0x3A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,before,after:fullMsPages(c),beforeRegisters,
    afterRegisters:registers(c),beforeProgram,afterProgram:program(c)};
}
const run=o=>runPrepared(prepare(o),o);
function runUnobserved(o={}) {
  const c=prepare(o),before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  finish(c,o);c.runFrames(3);aligned(c);
  return {calc:c,options:o,before,beforeRegisters,beforeProgram,after:fullMsPages(c),
    afterRegisters:registers(c),afterProgram:program(c)};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,move,readW,finish,runPrepared,run,runUnobserved,brief};
