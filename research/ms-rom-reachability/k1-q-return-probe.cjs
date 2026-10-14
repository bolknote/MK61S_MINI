#!/usr/bin/env node
'use strict';
// Bounded native candidate: remove U's marker after retaining old W twice.
// The 32-frame wait replaces two rejected actions of equal duration; it
// does not inspect the internal phase or prove arbitrary keyboard timing.
const retained=require('./k1-q-retained-probe.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const defaults={...historical.defaults,values:['811','-1.2E-42','833','844']};
function finish(c,o={},record=()=>{}) {
  retained.finish(c,{...o,saveQ:false,retainOnlyW:true,tail:[['F'],['В↑']]},record);
  record('return-phase');c.runFrames(o.returnDelay??32);
  const act=(stage,keys)=>{record(stage);c.pressSequence(keys).runFrames(o.settleFrames??8);};
  act('return-u',['F',',']);
  for(const [i,keys] of (o.returnTail??[]).entries())act('return-tail-'+i,keys);
}
const run=(o={})=>capture.run({...defaults,...o},finish);
if(require.main===module)console.log(JSON.stringify(historical.brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={defaults,finish,run};
