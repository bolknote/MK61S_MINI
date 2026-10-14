#!/usr/bin/env node
'use strict';
// Conditional formatter-driven read after the preserving V/W entry.
// Unlike LastX this candidate does not deliberately push the visible stack.
// No cleanup or whole-domain contract is implied.
const deep=require('./k1-repack-deep-clone-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...deep.defaults,nopLeadPhase:1};
function finish(c,o={},record=()=>{}) {
  deep.finish(c,{...o,afterClone:[],afterClonePhase:0},record);
  record('nop/phase');c.runFrames(o.nopLeadPhase??1);
  stack.act(c,record,'nop/read',['K','0']);
  for(const [i,keys] of (o.afterNop??[]).entries()) {
    record('nop/tail-phase-'+i);c.runFrames(o.afterNopPhases?.[i]??0);
    stack.act(c,record,'nop/tail-'+i,keys,o.afterNopWaits?.[i]??8);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','nop/read',...(o.afterNop??[]).map((_,i)=>'nop/tail-'+i)]);
module.exports={defaults,finish,run};
