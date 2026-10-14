#!/usr/bin/env node
'use strict';
// Experimental continuation after W clone/U removal. The 01 scanner may
// treat W as its origin, so a requested register is not its physical source.
// Whole-entry preservation and formatter safety are deliberately not assumed.
const entry=require('./probe_ms_clone_remove_u.cjs');
const clone=require('./probe_ms_marker_clone_w.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
function finish(c,o={},record=()=>{}) {
  const result=entry.finish(c,o,record);
  record('clone-load-x');c.pressSequence(['П→X',o.sourceKey??'8']).runFrames(o.settleFrames??8);
  for(const [i,keys] of (o.tailActions??[]).entries()) {
    record('clone-load-tail-'+i);c.pressSequence(keys).runFrames(o.settleFrames??8);
  }
  return result;
}
function prepare(o={}) {
  const c=entry.prepare(o);
  // Independent keyboard-only fixture data, before the live continuation.
  if(o.sourceValue!==undefined) {
    inputLiteral(c,o.sourceValue);c.pressSequence(['X→П','2']).runFrames(8);
  }
  return aligned(c);
}
const run=(o={})=>clone.runPrepared(prepare(o),o,finish);
function brief(r) {
  const es=r.traced.events;
  return {options:r.options,result:r.result,display:r.traced.display,before:r.before,after:r.after,
    registers:r.afterRegisters,program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    end:es.filter(e=>e.stage==='done'&&e.ring).slice(0,1).map(e=>Object.fromEntries(
      ['X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]))),
    paths:es.filter(e=>e.stage==='clone-load-x'&&[1,2,0xD6,0xEE,0xE7,0xE9,0xA9,0x40,0x47].includes(e.ip))
      .map(e=>[e.command,e.ip.toString(16),e.slot,e.raw,raw(e.m,0),raw(e.r,0),e.nextIp.toString(16)])};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,run,brief};
