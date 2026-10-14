#!/usr/bin/env node
'use strict';
// Exploratory upper-entry preparation, NOT an exchange or a safe exit.
// P0 is usable as scratch only after its original has been parked in Ms.
// Each claimed storage contract must be established by the native checker.
const stack=require('./k1-visible-stack-cycle.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
function readScratch(c,o={},record=()=>{}) {
  const a=(s,k,n)=>stack.act(c,record,s,k,n),displays=[];
  for(let attempt=0;attempt<3;attempt++) {
    const s='attempt-'+attempt+'/';
    if(attempt)for(let i=0;i<2;i++)a(s+'retry-'+i,['F',',']);
    a(s+'duplicate',['В↑']);
    for(const [i,k] of ['Сx','K','Сx','K','8'].entries())a(s+'marker-'+i,[k]);
    a(s+'zero',['Сx']);a(s+'store',['X→П','0']);a(s+'clean',['П→X','0']);
    record(s+'display');const d=c.displayText();displays.push(d);
    if(d==='0,')continue;
    if(!/^[0-9, +\-]+$/.test(d)||!/[1-9]/.test(d))throw new Error('Unexpected display: '+d);
    return {attempts:attempt+1,displays};
  }
  return {attempts:3,displays};
}
function readScratchAligned(c,o={},record=()=>{}) {
  const result=readScratch(c,o,record);
  // Each additional attempt is 118 frames, or +1 modulo the three ring
  // phases. Keep the successful one-attempt residue without a hidden read.
  record('phase');c.runFrames((1-result.attempts%3+3)%3);
  return result;
}
function finish(c,o={},record=()=>{}) {
  const a=(s,k,n)=>stack.act(c,record,s,k,n);
  const scratch=o.alignScratchRetries?readScratchAligned:readScratch;
  a('load-original-p0',['П→X','0']);
  stack.finish(c,o,s=>record('park-p0/'+s));
  scratch(c,o,s=>record('read-v/'+s));
  a('compact-v-w',['+']);
  a('guard-duplicate',['В↑']);
  if(o.zeroGuard)a('guard-input',['Сx'],36); // Same 38 frames as the nonzero literal.
  else a('guard-input',['Сx','1',',','2','3','4','5','6','7','8','/-/','ВП','4','2','/-/']);
  a('guard-tail-copy',['В↑']);a('guard-tail-rotate',['F',',']);
  stack.push(c,s=>record('park-guard/'+s));
  if(o.stopAfterGuard)return;
  scratch(c,o,s=>record('read-u/'+s));
  for(let i=0;i<2;i++)a('prepare-marker-rotate-'+i,['F',',']);
  a('prepare-marker-duplicate',['В↑']);
  for(const [i,k] of ['Сx','K','Сx','K','8'].entries()) {
    a('prepare-marker-'+i,[k]);
    // Research variant: change the INV result's exponent BEFORE fractional part clones
    // the marker into T. This does not neutralize the T marker's header.
    if(i===2&&o.plantMarkerExponent!==undefined)
      a('prepare-marker-exponent',['ВП',String(o.plantMarkerExponent)]);
  }
  if(o.neutralPlantMarker) {
    // Change only visible X AFTER the logical marker has also reached T.
    // This explores its later formatter; U will still receive the old T.
    a('prepare-marker-neutral-order-f',['ВП']);
    a('prepare-marker-neutral-order-1',['1']);
    if(o.neutralPlantRefresh)a('prepare-marker-neutral-refresh',['K','0']);
  }
  if(o.signBuffer) {
    a('sign-buffer-clear',['Сx']);
    for(const [i,keys] of (o.bufferCommands??[['K','5']]).entries())a('sign-buffer-'+i,keys);
    return;
  }
  a('plant-u',['П→X','9']);
  if(o.clearBeforeSwap)a('clear-before-swap',['Сx']);
  for(let i=0;i<(o.swaps??0);i++)a('clone-swap-'+i,['↔']);
  for(const [i,keys] of (o.tail??[]).entries())a('tail-'+i,keys,o.tailWaits?.[i]);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish);
if(require.main===module) {
  const r=run(JSON.parse(process.argv[2]||'{}'));
  const {raw}=require('./probe_ms_two_markers.cjs');
  const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
  const first=r.traced.events.find(e=>e.ring),original=snapshotFromRing(first.ring).words;
  const seen=new Set();
  const rows=r.traced.events.filter(e=>{if(!e.ring||seen.has(e.stage))return false;seen.add(e.stage);return true;})
    .map(e=>{const visible=Object.fromEntries(['X1','X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]));
      const live=[...snapshotFromRing(e.ring).words,...Object.values(visible)];
      return {stage:e.stage,visible,p0:raw(e.ring.U,0),lost:original.filter(w=>!live.includes(w))};});
  const wanted=['read-v/attempt-0/duplicate','compact-v-w','guard-tail-copy','park-guard/push',
    'read-u/attempt-0/duplicate','plant-u','clear-before-swap','sign-buffer-clear','sign-buffer','done'];
  console.log(JSON.stringify({rows:rows.filter(e=>wanted.includes(e.stage)||e.lost.length||e.stage.startsWith('clone-swap-')||e.stage.startsWith('tail-')||e.stage.startsWith('sign-buffer-')),
    registers:r.afterRegisters,ms:r.after,programHeld:JSON.stringify(r.afterProgram)===JSON.stringify(r.beforeProgram)},null,2));
}
module.exports={readScratch,readScratchAligned,finish,run};
