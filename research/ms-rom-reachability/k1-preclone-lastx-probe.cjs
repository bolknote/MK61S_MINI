#!/usr/bin/env node
'use strict';
// Diagnostic native keyboard candidate. Stop the established deep prefix
// before SIGN, then try to move the visible T marker to Y using LastX.
// This is not a preserving or closed K1 claim. No state is injected.
const deep=require('./k1-repack-deep-clone-probe.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...deep.defaults,precloneLeadPhase:0,precloneTail:[['F','В↑'],['K','×']]};
function finish(c,o={},record=()=>{}) {
  const stop={};
  try {
    deep.finish(c,o,s=>{if(s==='clone-prefix')throw stop;record(s);});
    throw new Error('Established prefix did not expose clone-prefix');
  } catch(e) {if(e!==stop)throw e;}
  record('preclone/phase');c.runFrames(o.precloneLeadPhase??0);
  for(const [i,keys] of (o.precloneTail??defaults.precloneTail).entries()) {
    record('preclone/tail-phase-'+i);c.runFrames(o.precloneTailPhases?.[i]??0);
    stack.act(c,record,'preclone/tail-'+i,keys,o.precloneTailWaits?.[i]??8);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  (o.precloneTail??defaults.precloneTail).map((_,i)=>'preclone/tail-'+i));
module.exports={defaults,finish,run};
