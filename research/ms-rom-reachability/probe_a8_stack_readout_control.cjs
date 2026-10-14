#!/usr/bin/env node
'use strict';
// A specifically derived, unsuccessful non-destructive-read candidate.
// It must remain a negative control: displaying U is not yet saving U/V.
const assert=require('node:assert/strict');
const marker=require('./probe_a8_marker_route.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function run({zeroCleanup=false}={}) {
  const options={values:['111','222','333','-1.2345678E-42'],seedLowDigit:0,
    clearKey:'8',markerLifts:1,markerLift:'recall-zero',finalRecall:false};
  const calc=marker.prepare(options),before=fullMsPages(calc),beforeProgram=program(calc);
  let stage='';const stages=[];
  const traced=trace(calc,c=>{
    marker.finish(c,options,s=>stage=s);
    const actions=zeroCleanup?
      [['read-u',['В↑']],['remove-marker-1',['П→X','3']],['remove-marker-2',['П→X','3']],
       ['rotate-1',['F',',']],['rotate-2',['F',',']],['save-u',['X→П','9']],
       ['clear',['Сx','В↑','В↑','В↑','+']]]:
      [['read-u',['В↑']],['shift-marker',['П→X','3']],
       ['read-v',['F','В↑']],['save-v',['X→П','2']],['rotate',['F',',']],
       ['swap',['↔']],['save-u',['X→П','9']],['clear',['Сx','В↑','В↑','В↑','+']]];
    for(const [label,keys] of actions) {
      stage=label;c.pressSequence(keys).runFrames(8);
      stages.push({stage,display:c.displayText()});
    }
    stage='done';c.runFrames(3);
  },{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    ringAt:e=>{e.stage=stage;return [0xEE,0xE7,0xAD,0x47,0xA8,0xA9].includes(e.ip);}});
  aligned(calc);
  return {calc,before,after:fullMsPages(calc),beforeProgram,afterProgram:program(calc),
    beforeOptions:options,afterRegisters:registers(calc),traced,stages};
}
if(require.main===module) {
  const r=run();
  const read=r.traced.events.find(e=>e.stage==='read-u'&&e.ip===0xEE&&e.slot==='U');
  assert.ok(read);assert.equal(read.raw,r.before.U.slice(2));
  assert.equal(r.stages.find(s=>s.stage==='read-u').display,'-1,2345678-42');
  const formattingWrite=r.traced.events.find(e=>e.stage==='read-u'&&e.ip===0xE7&&e.slot==='V');
  assert.ok(formattingWrite,'the following formatter writes outside the visible stack');
  assert.ok(r.traced.writes.some(w=>w.command===formattingWrite.command&&w.slot==='V'&&w.before!==w.value));
  assert.notDeepEqual(r.after,r.before);
  assert.notDeepEqual([r.afterRegisters[9],r.afterRegisters[2]],
    [r.before.U.slice(2),r.before.V.slice(2)]);
  assert.notDeepEqual(r.afterProgram,r.beforeProgram);
  console.log('PASS: negative control: EE reads full U and displays it, but the formatter subsequently writes V; the proposed stack-only readout is NOT non-destructive.');
  const cleaned=run({zeroCleanup:true});
  assert.equal(cleaned.afterRegisters[9],cleaned.before.U.slice(2));
  assert.deepEqual(cleaned.afterProgram,cleaned.beforeProgram);
  assert.ok(cleaned.traced.events.every(e=>e.ip!==0xC9));
  assert.deepEqual(cleaned.after,{...cleaned.before,V:cleaned.before.U});
  console.log('PASS: two zero recalls repair cleanup and preserve U/W/Q/P7..P10, but V is still overwritten with U: this is NOT nondestructive U readout.');
}
module.exports={run};
