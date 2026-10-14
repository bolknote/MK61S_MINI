#!/usr/bin/env node
'use strict';
// REJECTED candidate, not a safe reader. Two zero lifts leave m in Z.
// Native ENTER reads V; the formatter then reads X=V (NOT W) and can
// overwrite W with V before RCL E removes the marker. Kept only as a
// counterexample to the proposed slot-arithmetic argument. Never use as K1.
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
function finish(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);
  const act=(stage,keys,wait=o.settleFrames??8)=>{record(stage);c.pressSequence(keys).runFrames(wait);};
  act('safe-clear',['Сx','В↑','В↑','В↑','+']);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())act('safe-marker-'+i,[k],12);
  for(let i=0;i<2;i++) {
    act('safe-zero-'+i,['0']);
    act('safe-nop-'+i,['K','0']);
  }
  act('safe-read-W',['В↑']);
  act('safe-remove-T',['П→X','В↑']);
  act('safe-return-W',['F',',']);
  record('safe-phase');c.runFrames(2);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish);
if(require.main===module)console.log(JSON.stringify(historical.brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={finish,run};
