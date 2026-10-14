#!/usr/bin/env node
'use strict';
// Exploratory neutral-marker/visible-rotation routes, NOT a finished pair.
const prefix=require('./k1-two-hole-prefix.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const defaults={zeroGuard:true,neutralPlantMarker:true,neutralPlantRefresh:true,
  clearBeforeSwap:true,swaps:1,tail:[['F',',']]};
function finish(c,o={},record=()=>{}) {return prefix.finish(c,{...defaults,...o},record);}
function run(o={}) {
  o={...historical.defaults,...defaults,...o};
  return capture.run(o,finish,['prepare-marker-neutral-refresh','plant-u','clone-swap-0',
    ...o.tail.map((_,i)=>'tail-'+i)]);
}
function brief(r) {
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words,seen=new Set();
  const rows=r.traced.events.filter(e=>{if(!e.ring||seen.has(e.stage))return false;seen.add(e.stage);return true;})
    .map(e=>{const values=Object.fromEntries(['X1','X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]));
      const live=[...snapshotFromRing(e.ring).words,...Object.values(values)];
      return {stage:e.stage,values,p0:raw(e.ring.U,0),lost:original.filter(w=>!live.includes(w))};})
    .filter(e=>e.stage.startsWith('clone-swap-')||e.stage.startsWith('tail-')||e.stage==='done'||e.lost.length);
  const routes=r.traced.events.filter(e=>e.stage.startsWith('tail-')&&
    [0x9C,0xEE,0xE9,0xE7,0xA3,0xD6].includes(e.ip))
    .map(e=>({stage:e.stage,n:e.command,ip:e.ip.toString(16),slot:e.slot,next:e.nextIp.toString(16),
      m:raw(e.m),r:raw(e.r,0),s1:e.s1,sp:e.sp}));
  return {options:r.options,rows,routes,ms:r.after,registers:r.afterRegisters,
    programHeld:JSON.stringify(r.afterProgram)===JSON.stringify(r.beforeProgram)};
}
if(require.main===module)console.log(JSON.stringify(brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={defaults,finish,run,brief};
