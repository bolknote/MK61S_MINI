#!/usr/bin/env node
'use strict';
// Composition candidate: save U/V/W, exchange W/Q, read displaced Q,
// and write all four desired words back. P4..P7/P9 are explicit scratch.
// No synchronization, host register getter, or reset between stages.
const assert=require('node:assert/strict');
const u=require('./probe_ms_classic_u.cjs');
const v=require('./probe_ms_classic_v.cjs');
const w=require('./probe_ms_classic_w.cjs');
const swap=require('./probe_ms_shifted_swap.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');

const prepare=(options={})=>v.prepare({values:['111','222','333','444'],...options});
function finish(calc,options={},record=()=>{}) {
  assert.ok([0,1,2].includes(options.phaseOffset??0));
  assert.ok([undefined,false,true].includes(options.restore));
  assert.ok([undefined,'secondary','direct'].includes(options.qReader));
  calc.runFrames(options.phaseOffset??0);
  const local={...options,phaseOffset:0},wait=options.settleFrames??8;
  const under=name=>label=>record(name+'/'+label);
  u.finish(calc,local,under('read-u'));
  record('save-u-to-p4');calc.pressSequence(['П→X','9','X→П','4']).runFrames(wait);
  v.finish(calc,{...local,destination:5},under('read-v'));
  w.finish(calc,{...local,destination:7},under('read-w'));
  swap.finish(calc,{...local,lifts:3,save:false},under('exchange-wq'));
  if(options.qReader==='direct') {
    // Kept as the original phase-dependent negative control.
    w.finish(calc,{...local,destination:6},under('read-q'));
  } else {
    // W now holds the original Q. This reader can overwrite V, which is
    // already backed up in P5 and will be restored by the final four pushes.
    const rotations=options.robustQReturn?3:1;
    swap.finish(calc,{...local,lifts:2,postSwap:[['П→X','3'],['П→X','3'],
      ...Array.from({length:rotations},()=>['F',','])],save:true},under('read-q'));
    record('save-q-to-p6');calc.pressSequence(['П→X','9','X→П','6']).runFrames(wait);
  }
  if(options.restore) {
    // Order the backups as U,V,W,Q, so final writes restore the entire Ms
    // bank and leave a four-word readout in P4..P7. P9 is already scratch.
    record('order-original-wq');
    calc.pressSequence(['П→X','6','X→П','9','П→X','7','X→П','6','П→X','9','X→П','7']).runFrames(wait);
  }
  for(const source of ['7','6','5','4']) {
    record('source-p'+source);calc.pressSequence(['П→X',source,'X→П','9']).runFrames(wait);
    push.finish(calc,local,under('write-p'+source));
  }
  return calc;
}
function runPrepared(calc,options={}) {
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  assert.equal(beforeRegisters[3],'000000000000');
  let stage='',seen=new Set();
  const traced=trace(calc,c=>{finish(c,options,label=>{stage=label;});stage='done';c.runFrames(3);},
    {extraIps:[0x9C,0xE5,0xE6,0xE8,0xE7,0xA7,0xA8,0xA9,0xD4,0xD6,0xA2,0xA3],
      fullState:true,allWrites:true,
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xE7,0xA9,0xD4,0xA3].includes(e.ip);}});
  aligned(calc);return {calc,options,before,after:fullMsPages(calc),beforeRegisters,
    afterRegisters:registers(calc),beforeProgram,afterProgram:program(calc),traced};
}
const run=(options={})=>runPrepared(prepare(options),options);
function brief(r) {
  return {options:r.options,before:r.before,after:r.after,
    scratch:Object.fromEntries([4,5,6,7,9].map(n=>[n,r.afterRegisters[n]])),
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    reads:r.traced.events.filter(e=>['read-v/save-v-direct','read-w/save-v-direct','read-q/save-v-direct'].includes(e.stage)&&e.ip===0xEE)
      .map(e=>({stage:e.stage,slot:e.slot,raw:e.raw})),
    falseControls:r.traced.events.filter(e=>e.ip===0x9C&&e.slot==='U').map(e=>({stage:e.stage,raw:e.raw,next:e.nextIp.toString(16)}))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief};
