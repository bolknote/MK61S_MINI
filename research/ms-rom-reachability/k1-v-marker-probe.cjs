#!/usr/bin/env node
'use strict';
// Structural experiment: after the first upper rotation W=q is backed,
// V=0 is disposable, while v/w remain visibly in Y/Z. A tail-preserving
// X marker may therefore be cloned into V without consuming another
// ordinary register. This is NOT a verified entry or a usable exchange.
const prefix=require('./k1-two-hole-prefix.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const hist=require('./k1-puhov-ring-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
function finish(c,o={},record=()=>{}) {
  prefix.finish(c,{...o,plantMarkerExponent:undefined,stopAfterGuard:false,signBuffer:false,
    alignScratchRetries:true,zeroGuard:true,neutralPlantMarker:true,neutralPlantRefresh:true,
    clearBeforeSwap:true,swaps:0,tailWaits:[6],tail:o.cleanU?
      [['F',','],['F',','],['K'],['5'],['0']]:[['F',',']]},s=>record('entry/'+s));
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())
    stack.act(c,record,'marker-'+i,[k],12);
  for(const [i,keys] of (o.cloneCommand??[['K'],['5']]).entries())
    stack.act(c,record,'clone-'+i,keys);
  for(const [i,keys] of (o.afterClone??[]).entries())stack.act(c,record,'after-'+i,keys);
}
function run(o={}) {
  o={...hist.defaults,phaseOffset:1,values:['-1.2345678E-42','822','833','844'],...o};
  return cap.run(o,finish,['entry/tail-0','clone-0','clone-1',
    ...(o.afterClone??[]).map((_,i)=>'after-'+i)]);
}
function brief(r) {
  const es=r.traced.events,original=snapshotFromRing(es.find(e=>e.ring).ring).words,seen=new Set();
  const rows=es.filter(e=>e.ring&&!seen.has(e.stage)&&(seen.add(e.stage),true)).map(e=>{
    const values=Object.fromEntries(['X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'].map(n=>[n,raw(e.ring[n])]));
    const live=[...snapshotFromRing(e.ring).words,...Object.values(values)];
    return {stage:e.stage,command:e.command,values,missing:original.filter(x=>!live.includes(x))};
  }).filter(e=>!e.stage.startsWith('entry/')||e.stage==='entry/tail-0'||e.missing.length);
  const routes=es.filter(e=>!e.stage.startsWith('entry/')&&[0x9C,0xEE,0xE9,0xE7,0xA3].includes(e.ip))
    .map(e=>({stage:e.stage,command:e.command,ip:e.ip.toString(16),slot:e.slot,next:e.nextIp.toString(16),
      m:raw(e.m),r:raw(e.r,0),sp:e.sp}));
  return {options:r.options,rows,routes,before:r.before,after:r.after,
    registers:r.afterRegisters,programHeld:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram)};
}
if(require.main===module)console.log(JSON.stringify(brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={finish,run,brief};
