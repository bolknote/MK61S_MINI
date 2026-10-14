#!/usr/bin/env node
'use strict';
// Candidate preserving W reader. A typed zero after NOP lifts the marker
// without requiring a pre-existing short ordinary register. Three lifts
// leave the only extra marker in T; ENTER then drops it before formatting W.
// Numeric/control universality requires separate checks, not this comment.
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
function finish(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);
  const act=(stage,keys,wait=o.settleFrames??8)=>{record(stage);c.pressSequence(keys).runFrames(wait);};
  act('reader-clear',['Сx','В↑','В↑','В↑','+']);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())act('reader-marker-'+i,[k],12);
  for(let i=0;i<3;i++) {
    act('reader-zero-'+i,['0']);
    act('reader-nop-'+i,['K','0']);
  }
  act('reader-read-W',['В↑']);
  // Preserve the old reader's duration modulo three frames for compositions.
  record('reader-phase');c.runFrames(1);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish);
if(require.main===module)console.log(JSON.stringify(historical.brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={finish,run};
