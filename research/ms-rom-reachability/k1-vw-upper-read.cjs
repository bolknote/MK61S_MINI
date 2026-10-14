#!/usr/bin/env node
'use strict';
// Conditional preserving read through the late formatter. LastX initially
// pushes V's marker, NOT the upper payload. No closed exit is implied.
const deep=require('./k1-repack-deep-clone-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...deep.defaults};
function finish(c,o={},record=()=>{}) {
  deep.finish(c,{...o,afterClonePhase:0,afterClone:[['F','В↑']],afterCloneWaits:[8]},record);
  if(o.afterReadPhase){record('after-read-phase');c.runFrames(o.afterReadPhase);}
  for(const [i,keys] of (o.afterRead??[]).entries())
    stack.act(c,record,'after-read-'+i,keys,o.afterReadWaits?.[i]??8);
}
const run=(o={})=>cap.run({...defaults,...o},finish,['clone-prefix','clone-sign','after-clone-0',
  ...(o.afterRead??[]).map((_,i)=>'after-read-'+i)]);
module.exports={defaults,finish,run};
