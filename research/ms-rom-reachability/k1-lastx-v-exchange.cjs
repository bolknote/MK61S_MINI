#!/usr/bin/env node
'use strict';
// Research branch: retain U in the visible stack before a write at V.
// This probe makes no claim of a completed pair or preserved whole bank.
const p=require('./k1-bank-v-capture.cjs');
function finish(c,o={},record=()=>{}) {
  p.finish(c,{...o,tail:undefined},record);
  const actions=o.splitLastX?[['F'],['В↑']]:[['F','В↑']];
  actions.push(...(o.afterLastX??[]));
  for(const [i,keys] of actions.entries()) {
    record('lastx-tail-'+i);c.pressSequence(keys).runFrames(o.settleFrames??8);
  }
}
const run=(o={})=>p.run(o,finish);
module.exports={finish,run};
