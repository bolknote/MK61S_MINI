#!/usr/bin/env node
'use strict';
// Conditional native writer: replace Ms P7, preserve P8/P9/P10, remove V.
// One guarded left rotation followed by a compensated M1->upper-stack push.
// Lower Ms is modified by entry/exit. This is not a full-Ms restore or K1.
const compact=require('./probe_ms_upper_compact_exit.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
function preparePointers(c) {
  inputLiteral(c,'10');c.pressSequence(['X→П','Сx','K','П→X','Сx']);
  inputLiteral(c,'2');c.pressSequence(['X→П','6']);
  return c;
}
function prepareScratch(c,o={},record=()=>{}) {
  compact.prepareScratch(c,{...o,postPointer:o.postPointer??'110'},record);
  record('writer-pointers');return preparePointers(c);
}
function prepare(o={}) {
  const local={...o,postPointer:o.postPointer??'110'};
  const c=o.fullUpper?compact.prepareScratch(require('./prepare_ms_full_upper_fixture.cjs').prepare(o),local):compact.prepare(local);
  inputLiteral(c,o.source??'-8.7654321E-17');c.pressSequence(['X→П',',']);
  preparePointers(c);
  return aligned(c);
}
function optionsFor(o={}) {
  const result=compact.optionsFor(o);
  // Unlike a reader, this writer does not need a backup of the old top.
  // Its direct-store formatter can spill -1E-99 into U and break re-entry.
  if(!o.legacyCopy)result.tailActions=result.tailActions.filter(a=>a[0]!=='upper-copy-fifth');
  result.tailActions.find(a=>a[0]==='upper-swap')[1]=['F',','];
  result.tailActions.find(a=>a[0]==='upper-after-0')[1]=['K','П→X','Сx'];
  return result;
}
const finish=(c,o={},record=()=>{})=>two.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>two.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  return {options:r.options,before:r.before,after:r.after,registers:r.afterRegisters,
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    path:r.traced.events.filter(e=>['upper-swap','upper-after-0','upper-after-5','upper-after-6'].includes(e.stage)&&
      [0xA3,0xD6,0xD4,0xEE,0xE7].includes(e.ip))
      .map(e=>[e.stage,e.ip.toString(16),e.slot,two.raw(e.m,0),e.raw,two.raw(e.r,0),e.nextIp.toString(16)]),
    end:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,two.raw(r.traced.events.findLast(e=>e.ring).ring[n])]))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,preparePointers,prepareScratch,finish,runPrepared,run,brief,optionsFor};
