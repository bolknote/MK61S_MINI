#!/usr/bin/env node
'use strict';
// A genuine bidirectional lower-half exchange, not Ms restoration.
// P0..P3 <-> U/V/W/Q; P4..P8 and upper Ms retained; P9/A/B/C/D/E scratch.
// Native entry-domain and timing claims belong to the integration tests.
const assert=require('node:assert/strict');
const fixture=require('./prepare_ms_full_upper_fixture.cjs');
const u=require('./probe_ms_classic_u.cjs');
const v=require('./probe_ms_classic_v.cjs');
const w=require('./probe_ms_classic_w.cjs');
const {readQ}=require('./probe_ms_read8_roundtrip.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const under=(record,prefix)=>label=>record(prefix+'/'+label);
const clear=['Сx','В↑','В↑','В↑','+'];
function prepare(o={}) {
  const c=fixture.prepare({stress:true,fullUpper:['1111','2222','3333','4444'],values:['11','22','33','44'],...o});
  const bank=o.bank??['201','202','203','204'];assert.equal(bank.length,4);
  for(let i=0;i<4;i++){inputLiteral(c,bank[i]);c.pressSequence(['X→П',String(i)]).runFrames(8);}
  return aligned(c);
}
function move(c,from,to,o,record,label) {
  record(label);c.pressSequence(['П→X',from,'X→П',to]).runFrames(o.settleFrames??8);
}
function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0},wait=o.settleFrames??8;
  if(!o.skipSaveP3)move(c,'3','В↑',local,record,'save-original-p3');
  record('zero-p3');inputLiteral(c,'0');c.pressSequence(['X→П','3']).runFrames(wait);
  u.finish(c,local,under(record,'read-u'));
  move(c,'9',',',local,record,'keep-u-in-a');
  v.finish(c,{...local,destination:9},under(record,'read-v'));
  move(c,'9','/-/',local,record,'keep-v-in-b');
  w.finish(c,{...local,destination:9},under(record,'read-w'));
  move(c,'9','ВП',local,record,'keep-w-in-c');
  readQ(c,local,under(record,'read-last'));
  move(c,'9','Сx',local,record,'keep-q-in-d');
  for(const source of o.forwardWrites?['0','1','2','В↑']:['В↑','2','1','0']) {
    move(c,source,'9',local,record,'source-'+source);
    push.finish(c,local,under(record,'write-'+source));
  }
  for(const [from,to] of [[',','0'],['/-/','1'],['ВП','2'],['Сx','3']])
    move(c,from,to,local,record,'output-'+to);
  record('clear-final');c.pressSequence(clear).runFrames(wait);return c;
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  let stage='',seen=new Set();
  const short=new Set([0xAC,0xEE,0xDE,0x9C,0xC9,0xD4,0xD6,0xA2,0xA3,0xE5,0xE6,0xE8,0xA7,0xE7,0xA8,0xA9,0xA5,0x47]);
  const secondary=()=>stage==='read-u/swap-read-u'||stage==='read-u/save-u'||stage.endsWith('/shifted-swap')||stage.includes('/post-swap-');
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||secondary()||short.has(ip),otherChipsAt:secondary,
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xA9,0xA5,0xD4,0xD6,0x47].includes(e.ip)||[0x53,0x4E,0x2A,0x3A,0x39].includes(e.otherChips?.[4].ip);}});
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
function brief(r) {
  return {before:r.before,after:r.after,bankBefore:r.beforeRegisters.slice(0,4),bankAfter:r.afterRegisters.slice(0,4),
    upperRegistersHeld:JSON.stringify(r.beforeRegisters.slice(4,9))===JSON.stringify(r.afterRegisters.slice(4,9)),
    scratch:r.afterRegisters.slice(9),program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,move,finish,runPrepared,run,runUnobserved,brief};
