#!/usr/bin/env node
'use strict';
// Research composition: four lower backups plus four upper readouts.
// The upper a word lives in lower V/Q while b stays in ordinary P8.
// Writer D/E are retained instead of preparing their spare pointer values.
// Reader E is parked in P9 while A transports the temporary entry marker.
// Entry constraints and full restoration are test obligations, not assumed.
const assert=require('node:assert/strict');
const fixture=require('./prepare_ms_full_upper_fixture.cjs');
const lower=require('./probe_ms_wq_repair.cjs');
const upper=require('./probe_ms_upper_read4.cjs');
const two=require('./probe_ms_two_markers.cjs');
const writer=require('./probe_ms_writer_single_pointer.cjs');
const push=require('./probe_ms_p9_push.cjs');
const shifted=require('./probe_ms_shifted_swap.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const clear=['Сx','В↑','В↑','В↑','+'];
const under=(record,prefix)=>label=>record(prefix+'/'+label);
function prepare(o={}) {
  const c=fixture.prepare({stress:true,fullUpper:['1111','2222','3333','4444'],values:['11','22','33','44'],...o});
  inputLiteral(c,o.initialE??'-1E-99');c.pressSequence(['X→П','В↑']).runFrames(8);
  return aligned(c);
}
function move(c,source,destination,o,record,label) {
  record(label);c.pressSequence(['П→X',source,'X→П',destination]).runFrames(o.settleFrames??8);
}
function readerScratch(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8;
  const late=String(o.postPointer??110);assert.ok(['110','111'].includes(late));
  if(!o.unsafeSpareE)move(c,'В↑','9',o,record,'save-e-in-p9');
  record('compact-payload-marker');
  for(const key of ['Сx','K','-','ВП','K','0'])c.press(key).runFrames(12);
  c.pressSequence(['X→П','2']).runFrames(wait);
  for(let i=0;i<4;i++)c.pressSequence(['П→X','3']).runFrames(wait);
  c.pressSequence(clear).runFrames(wait);
  // Late U-based DC must fetch P3=0, not P4=guard. The latter can be
  // formatted into U and become false control for the following Q read.
  for(const [value,key] of [[late,'0'],['-1.2345678E-42','4'],['9','5'],['10','ВП'],['9','7'],...(o.unsafeSpareE?[]:[['2','В↑']])]) {
    record('compact-constant-'+key);inputLiteral(c,value);c.pressSequence(['X→П',key]).runFrames(wait);
  }
  record('compact-normalize-p5');c.pressSequence(['K','П→X','5']).runFrames(wait);
}
function readUpper(c,o,i,record) {
  readerScratch(c,o,record);
  two.finish(c,upper.rotationOptions({...o,keepP8:i!==0,payloadKey:o.unsafeSpareE?'9':','},i===0),record);
  if(!o.unsafeSpareE)move(c,'9','В↑',o,record,'restore-e');
}
function readQ(c,o={},record=()=>{}) {
  shifted.finish(c,{...o,lifts:3,save:false},under(record,'exchange-wq'));
  shifted.finish(c,{...o,lifts:2,postSwap:[['П→X','3'],['П→X','3'],['F',','],['F',','],['F',',']],save:true},under(record,'read-q'));
}
function parkP9(c,o,record,zeroKey='3') {
  push.finish(c,o,under(record,'to-u'));
  move(c,zeroKey,'9',o,record,'zero-source');
  push.finish(c,o,under(record,'to-v'));
}
function saveP3(c,o,record) {
  move(c,'3','7',o,record,'save-p3-in-p7');
  record('zero-p3');inputLiteral(c,'0');c.pressSequence(['X→П','3']).runFrames(o.settleFrames??8);
}
function bridge(c,o,record) {
  saveP3(c,o,record);readQ(c,o,record);parkP9(c,o,record,'0');
  move(c,'7','3',o,record,'restore-p3');
}
function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0,legacyBridgeReturn:false,keepE:true};
  const wait=o.settleFrames??8;
  record('initial-zero-p3');inputLiteral(c,'0');c.pressSequence(['X→П','3']).runFrames(wait);
  lower.finish(c,{...local,restore:true,robustQReturn:!o.legacyLowerReturn},under(record,'backup-four'));
  for(const [a,b] of [['6','/-/'],['7','Сx'],['4','1'],['5','6']])move(c,a,b,local,record,'relocate-'+a+'-'+b);
  move(c,'3','9',local,record,'initial-zero-source');push.finish(c,local,under(record,'initial-zero-u'));
  readUpper(c,local,0,under(record,'read-0'));
  move(c,'8','9',local,record,'park-a-source');parkP9(c,local,under(record,'park-a'));
  move(c,',','8',local,record,'save-b-in-p8');
  readUpper(c,local,1,under(record,'read-1'));
  move(c,',','В↑',local,record,'save-c-in-e');
  readQ(c,local,under(record,'bridge-reader-a'));parkP9(c,local,under(record,'bridge-reader-a'));
  readUpper(c,local,2,under(record,'read-2'));
  readQ(c,local,under(record,'read-final-a'));
  move(c,'9','ВП',local,record,'save-a-in-c');
  record('eight-readouts');
  if(o.readOnly) {
    move(c,'3','9',local,record,'final-zero-source');
    for(let i=0;i<4;i++)push.finish(c,local,under(record,'clear-lower-'+i));
    for(let i=0;i<4;i++){record('clear-visible-'+i);c.pressSequence(['П→X','3']).runFrames(wait);}
    record('clear-final');c.pressSequence(clear).runFrames(wait);return c;
  }
  move(c,'6','3',local,record,'lower-v-to-p3');
  saveP3(c,local,under(record,'park-writer-a'));
  move(c,'ВП','9',local,record,'park-writer-a/source');parkP9(c,local,under(record,'park-writer-a'));
  move(c,'7','3',local,record,'park-writer-a/restore-p3');
  for(const [name,index] of [['d',10],['c',14],['b',8]]) {
    writer.finish(c,{...local,sourceIndex:index,keepP8:true},under(record,'write-'+name));
    if(name!=='b')bridge(c,local,under(record,'bridge-after-'+name));
  }
  // Exchange buffer responsibilities: a enters A, d waits in V for the
  // last upper push. C is free between writers and can hold a briefly.
  saveP3(c,local,under(record,'exchange-buffer'));
  readQ(c,local,under(record,'exchange-buffer'));
  move(c,'9','ВП',local,record,'exchange-buffer/a-to-c');
  move(c,',','9',local,record,'exchange-buffer/d-source');
  parkP9(c,local,under(record,'exchange-buffer'),'0');
  move(c,'ВП',',',local,record,'exchange-buffer/a-to-a');
  move(c,'7','3',local,record,'exchange-buffer/restore-p3');
  writer.finish(c,{...local,sourceIndex:10,keepP8:true},under(record,'write-a'));
  saveP3(c,local,under(record,'restore-all'));
  readQ(c,local,under(record,'restore-all'));
  move(c,'9','6',local,record,'restore-all/d-to-p6');
  move(c,'7','5',local,record,'restore-all/lower-v-to-p5');
  for(const source of ['Сx','/-/','5','1']) {
    move(c,source,'9',local,record,'restore-source-'+source);
    push.finish(c,local,under(record,'restore-lower-'+source));
  }
  for(let i=0;i<4;i++){record('clear-visible-'+i);c.pressSequence(['П→X','0']).runFrames(wait);}
  record('clear-final');c.pressSequence(clear).runFrames(wait);return c;
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
  const names=['U','V','W','Q','P7','P8','P9','P10'],outputs=r.options.readOnly?[1,6,11,13,12,8,14,10]:[1,5,11,13,10,8,14,6];
  return {before:r.before,after:r.after,registers:r.afterRegisters,
    copies:outputs.map((reg,i)=>({word:names[i],reg,expected:r.before[names[i]].slice(2),actual:r.afterRegisters[reg]})),
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    pointerEntries:r.traced.events.filter(e=>e.stage.endsWith('/upper-after-4')&&e.ip===0xD6)
      .map(e=>[e.stage,e.slot,two.raw(e.m,0)]),
    boundaries:['read-0/prepare-zero-p8','park-a-source','read-1/prepare-zero-p8','save-c-in-e','read-2/prepare-zero-p8','read-final-a/exchange-wq/clear-before',
      'save-a-in-c','lower-v-to-p3','write-d/zero-p0','write-c/zero-p0','write-b/zero-p0','write-a/zero-p0','restore-all/d-to-p6','done']
      .map(stage=>{const e=r.traced.events.find(e=>e.stage===stage&&e.ring);return e&&{stage,ms:names.map(n=>two.raw(e.ring[n]))};})};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,readerScratch,readUpper,readQ,parkP9,saveP3,bridge,finish,runPrepared,run,brief};
