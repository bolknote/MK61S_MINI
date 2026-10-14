#!/usr/bin/env node
'use strict';
// Conditional native cycle: the tail-preserving marker places the old hub
// in U during T/U/V/W push. The initial W reader is not format-universal.
const historical=require('./k1-puhov-ring-probe.cjs');
const capture=require('./k1-bank-v-capture.cjs');
function finish(c,o={},record=()=>{}) {
  if(o.reader==='x1-retry') {
    const result=require('./k1-x1-retry-reader.cjs').finish(c,o,record);
    // Match the legacy/new reader's duration modulo 3 after any retry count.
    record('cycle-reader-phase');c.runFrames((2-result.attempts%3+3)%3);
  } else if(o.reader==='zero-nop')require('./k1-zero-nop-reader.cjs').finish(c,o,record);
  else historical.finish(c,{...o,rotate:false,readLifts:6,tail:[]},record);
  const act=(stage,keys,wait=o.settleFrames??8)=>{record(stage);c.pressSequence(keys).runFrames(wait);};
  const hub=o.hubKey??'0';
  for(const [stage,keys] of [
    ['cycle-retain-a',['П→X',hub]],['cycle-retain-b',['П→X',hub]],
    ['cycle-rotate-a',['F',',']],['cycle-rotate-b',['F',',']],['cycle-swap',['↔']],
  ])act(stage,keys);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())act('cycle-marker-'+i,[k],12);
  record('cycle-phase');c.runFrames(o.cycleDelay??2);
  act('cycle-push',['П→X','9']);
  for(const [i,keys] of (o.cycleTail??[['Сx'],['+'],['X→П',hub]]).entries())act('cycle-tail-'+i,keys);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish);
if(require.main===module)console.log(JSON.stringify(historical.brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={finish,run};
