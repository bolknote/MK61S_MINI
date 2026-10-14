#!/usr/bin/env node
'use strict';
// Candidate native Ms P7/P8 exchange, entered with an internal V marker.
// This probe does not claim an intact-Ms return or a sixth-word readout.
const two=require('./probe_ms_two_markers.cjs');
const fixture=require('./prepare_ms_upper_fixture.cjs');
const prepare=(o={})=>o.enriched===false?two.prepare(o):fixture.prepare(o);
const optionsFor=(o={})=>({...o,shifts:1,reads:true,traceAll:true,traceSecondary:true,
  tailActions:[...(o.fifthCopyKey===undefined?[]:[['upper-copy-fifth',['X→П',o.fifthCopyKey]]]),
    ...Array.from({length:o.visibleLifts??3},(_,i)=>['upper-lift-'+i,['П→X','3']]),
    ...(o.beforeSwapKeys?[['upper-prime',o.beforeSwapKeys]]:[]),
    ['upper-swap',o.sourceKeys??['↔']],...(o.afterKeys||[]).map((keys,i)=>['upper-after-'+i,keys])]});
const finish=(c,o={},record=()=>{})=>two.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>two.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  const es=r.traced.events,unique=xs=>[...new Set(xs.map(JSON.stringify))].map(JSON.parse);
  return {before:r.before,after:r.after,registers:r.afterRegisters,display:r.traced.display,
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    primary:unique(es.filter(e=>e.stage==='upper-swap'||e.stage.startsWith('upper-after'))
      .filter(e=>[0x9C,0xAA,0xA2,0xA3,0xEE,0xE7,0xE9,0xD4,0xD6].includes(e.ip))
      .map(e=>({stage:e.stage,ip:e.ip.toString(16),slot:e.slot,raw:e.raw,next:e.nextIp.toString(16)}))),
    secondary:unique(es.filter(e=>e.stage==='upper-swap'||e.stage.startsWith('upper-after'))
      .filter(e=>[0x53,0x4E,0x2A,0x27].includes(e.otherChips?.[4].ip))
      .map(e=>{const c=e.otherChips[4];return {stage:e.stage,ip:c.ip.toString(16),slot:c.slot,raw:two.raw(c.m),
        fields:[c.l,c.s1,c.r[32],c.r[35],c.r[41]]};}))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,optionsFor,brief};
