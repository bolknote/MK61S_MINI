#!/usr/bin/env node
'use strict';
// Experiment: prepare nonzero T before planting U. An ordinary A carrier
// places A7 on X, skipping the visible X marker and selecting Y for the
// lower push. Reachability and the subsequent formatter are NOT assumed.
const clone=require('./probe_ms_marker_clone_w.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const prepare=(o={})=>clone.prepare({values:['111','222','-1.2345678E-42','444'],...o});
function finish(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8,mwait=o.markerFrames??12;
  const act=(name,keys,frames=wait)=>{record('clone-'+name);c.pressSequence(keys).runFrames(frames);};
  c.runFrames(o.phaseOffset??0);
  act('clear-start',['Сx','В↑','В↑','В↑','+']);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())act('marker-'+i,[k],mwait);
  for(const k of [',','В↑','6'])act('save-marker-'+k,['X→П',k]);
  for(let i=0;i<4;i++)act('remove-marker-'+i,['П→X','3']);
  act('clear-source',['Сx','В↑','В↑','В↑','+']);
  record('clone-tail-number');inputLiteral(c,o.tailValue??'-1.2345678E-42');c.runFrames(wait);
  act('zero-before-two',['П→X','3']);
  act('source-0',['П→X','В↑']);act('source-1',['П→X','В↑']);
  act('plant-a',['П→X',',']);
  for(let i=0;i<(o.swaps??1);i++)act('swap-'+i,['↔']);
  return c;
}
const runPrepared=(c,o={})=>clone.runPrepared(c,o,finish);
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  const es=r.traced.events;
  return {options:r.options,before:r.before,after:r.after,registers:r.afterRegisters,
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    stages:es.filter(e=>e.ring).filter((e,i,a)=>!i||e.stage!==a[i-1].stage)
      .filter(e=>['clone-zero-before-two','clone-source-0','clone-source-1','clone-plant-a','done'].includes(e.stage)||e.stage.startsWith('clone-swap-'))
      .map(e=>({stage:e.stage,words:Object.fromEntries(['X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'].map(n=>[n,raw(e.ring[n])]))})),
    paths:es.filter(e=>['clone-plant-a','clone-swap-0'].includes(e.stage)&&[0xD6,0xEE,0xE7,0xE9,0xA9,0x40,0x47].includes(e.ip))
      .map(e=>[e.stage,e.command,e.ip.toString(16),e.slot,e.raw,raw(e.r,0),e.nextIp.toString(16)])};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,runPrepared,run,brief};
