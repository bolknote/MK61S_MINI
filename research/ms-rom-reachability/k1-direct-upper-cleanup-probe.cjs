#!/usr/bin/env node
'use strict';
// Exploratory suffixes, not a clean exchange. New runs always replay the
// whole keyboard prefix; no imports or interior-state continuation.
const bridge=require('./k1-direct-upper-bridge.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
function finish(c,o={},record=()=>{}) {
  bridge.finish(c,o,record);
  for(const [i,keys] of (o.cleanup??[]).entries())
    stack.act(c,record,'cleanup-'+i,keys);
}
function run(o={}) {
  return capture.run({...historical.defaults,...o},finish,
    (o.cleanup??[]).map((_,i)=>'cleanup-'+i));
}
function brief(r) {
  const original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  const seen=new Set(),rows=[];
  for(const e of r.traced.events)if(e.ring&&!seen.has(e.stage)) {
    seen.add(e.stage);
    const visible=Object.fromEntries(['X1','X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]));
    const live=[...snapshotFromRing(e.ring).words,...Object.values(visible)];
    const lost=original.filter(w=>!live.includes(w));
    if(e.stage.startsWith('cleanup-')||e.stage==='done'||lost.length)
      rows.push({stage:e.stage,visible,p0:raw(e.ring.U,0),lost});
  }
  return {rows,registers:r.afterRegisters,ms:r.after,
    programHeld:JSON.stringify(r.afterProgram)===JSON.stringify(r.beforeProgram),
    routes:r.traced.events.filter(e=>e.stage.startsWith('cleanup-')&&
      [0x9C,0xD6,0xEE,0xE7,0xE9,0xA3,0xA8].includes(e.ip))
      .map(e=>({stage:e.stage,n:e.command,ip:e.ip.toString(16),slot:e.slot,
        next:e.nextIp.toString(16),m:raw(e.m),r:raw(e.r,0),s1:e.s1,sp:e.sp}))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={finish,run,brief};
