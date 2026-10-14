#!/usr/bin/env node
'use strict';
// Conditional ordinary-P0 -> upper-P7 write. Old upper P7 is backed in W
// by the preceding NOP. Lower u/q still need a preserving exit afterwards.
const nop=require('./k1-vw-nop-read.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...nop.defaults,fullUpper:['-1E-99','9022','9033','9044'],
  writeLeadPhase:0};
function finish(c,o={},record=()=>{}) {
  nop.finish(c,{...o,afterNop:[['П→X','0']],afterNopPhases:[o.writeLeadPhase??0]},record);
  for(const [i,keys] of (o.afterWrite??[]).entries()) {
    record('write/tail-phase-'+i);c.runFrames(o.afterWritePhases?.[i]??0);
    stack.act(c,record,'write/tail-'+i,keys,o.afterWriteWaits?.[i]??8);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','nop/read','nop/tail-0',
    ...(o.afterWrite??[]).map((_,i)=>'write/tail-'+i)]);
module.exports={defaults,finish,run};
