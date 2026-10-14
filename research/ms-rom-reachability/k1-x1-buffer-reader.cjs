#!/usr/bin/env node
'use strict';
// Conditional native resource, NOT a full K1 or a phase-universal reader.
// P0 temporarily holds m; its original 12 tetras survive in X1 while W is read.
// No inspection, alignment or state substitution inside the live operation.
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const marker='0000F0000000';
function prime(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);
  // The extra preparation is 82 frames (1 mod 3); compensate explicitly.
  record('buffer-phase');c.runFrames(2);
  const act=(stage,keys,wait=8)=>{record(stage);c.pressSequence(keys).runFrames(wait);};
  act('buffer-clear',['Сx','В↑','В↑','В↑','+']);
  for(let i=0;i<3;i++)act('buffer-load-p-'+i,['П→X','0']);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())act('buffer-marker-'+i,[k],12);
  act('buffer-store-marker',['X→П','0']);
  act('buffer-drop-marker',['Сx','+']);
  act('buffer-save-x1',['↔']);
  act('buffer-recall-marker',['П→X','0']);
  for(let i=0;i<3;i++) {
    act('buffer-zero-'+i,['0']);
    act('buffer-nop-'+i,['K','0']);
  }
}
function finish(c,o={},record=()=>{}) {
  prime(c,o,record);
  const act=(stage,keys)=>{record(stage);c.pressSequence(keys).runFrames(8);};
  act('buffer-read-W',['В↑']);
  if(o.restore) {
    act('buffer-recall-original',['F','В↑']);
    act('buffer-restore-p0',['X→П','0']);
  }
  for(const [i,keys] of (o.bufferTail??[]).entries())act('buffer-tail-'+i,keys);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish);
if(require.main===module)console.log(JSON.stringify(historical.brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={marker,prime,finish,run};
