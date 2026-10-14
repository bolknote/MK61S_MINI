#!/usr/bin/env node
'use strict';
// Passive, all-chip diagnosis of the stale formatter after a native swap.
// Optional continuations are experiments, not automatically safe protocols.
const exit=require('./probe_ms_upper_read2_exit.cjs');
const upper=require('./probe_ms_upper_swap.cjs');
const indirect=require('./probe_ms_upper_indirect.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
function optionsFor(o={}) {
  const options=upper.optionsFor(indirect.optionsFor(exit.optionsFor(o)));
  const swap=options.tailActions.findIndex(a=>a[0]==='upper-swap');
  if(o.primeKeys)options.tailActions.splice(swap,0,['upper-prime',o.primeKeys]);
  if(o.mode==='program') {
    options.tailActions=options.tailActions.filter(a=>!a[0].startsWith('upper-after-'));
    options.tailActions.find(a=>a[0]==='upper-swap')[1]=['С/П'];
  }
  return options;
}
function prepare(o={}) {
  const c=exit.prepare(o);
  if(o.mode==='program')c.pressSequence(['В/О','F','ВП','↔','K','X→П','ВП','С/П','F','/-/','В/О']);
  return aligned(c);
}
const finish=(c,o={},record=()=>{})=>two.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>two.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
function analyze(r) {
  const es=r.traced.events.filter(e=>e.stage==='upper-swap');
  const request=es.find(e=>e.ip===0xA3&&e.slot==='W');
  const read=es.find(e=>e.command>request?.command&&e.ip===0xEE&&e.slot==='P7'&&e.nextIp===0xE3);
  const write=es.find(e=>e.command>request?.command&&e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='P7');
  const formatted=es.find(e=>e.command>write?.command&&e.ip===0xE7&&e.nextIp===0x47);
  const origin=request?.command??es[0]?.command??0;
  const phase=e=>e&&{t:e.command-origin,ip:e.ip.toString(16),slot:e.slot,
    a:two.raw(e.r,0),m:e.raw,next:e.nextIp.toString(16)};
  const ack=es.find(e=>e.command>request?.command&&e.otherChips?.[4].ip===0x27&&e.otherChips[4].slot==='W');
  const start=es.findLastIndex(e=>e.command<formatted?.command&&e.ip===0x40);
  return {before:r.before,after:r.after,registers:r.afterRegisters,
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    request:phase(request),acceptedControls:es.filter(e=>e.command>request?.command&&e.command<read?.command&&
      e.ip===0x9C&&e.nextIp===0x9E).map(phase),
    acknowledgement:ack&&{t:ack.command-origin,ip:'27',slot:'W'},
    cached:phase(read),secondaryWrite:write&&{
      t:write.command-request.command,ip:'4e',slot:write.otherChips[4].slot,
      a:two.raw(write.otherChips[4].r,0),m:two.raw(write.otherChips[4].m)},
    formatter:phase(formatted),
    suffix:start<0?[]:es.slice(start,es.indexOf(formatted)+1).map(e=>[e.ip.toString(16),e.slot]),
    c9:r.traced.events.filter(e=>e.ip===0xC9).map(e=>[e.command,e.slot]),
    prime:r.traced.events.filter(e=>e.stage==='upper-prime'&&[0xD6,0xEE,0xE7].includes(e.ip)).map(phase)};
}
if(require.main===module)console.log(JSON.stringify(analyze(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,optionsFor,analyze};
