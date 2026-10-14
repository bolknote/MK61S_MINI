#!/usr/bin/env node
'use strict';
// Clear the disposable visible X so late formatting cannot overwrite the
// W/Q exchange. This driver makes no whole-domain or clean-exit claim.
const add=require('./k1-u-reserve-masked-add.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...add.defaults};
function finish(c,o={},record=()=>{}) {
  add.finish(c,{...o,afterAdd:[],afterAddPhases:[],afterAddWaits:[]},record);
  if(!o.omitZeroGuard) {
    stack.act(c,record,'zero-swap/clear',['Сx']);
    record('zero-swap/phase');c.runFrames(2);
  }
  stack.act(c,record,'zero-swap/exchange',['↔']);
  for(const [i,keys] of (o.afterZeroSwap??[]).entries()) {
    if(o.afterZeroSwapPhases?.[i]){record('zero-swap/phase-'+i);c.runFrames(o.afterZeroSwapPhases[i]);}
    stack.act(c,record,'zero-swap/tail-'+i,keys,o.afterZeroSwapWaits?.[i]??8);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0',
    ...[0,1,2].map(i=>'u-reserve/tail-'+i),
    'zero-swap/clear','zero-swap/exchange',
    ...(o.afterZeroSwap??[]).map((_,i)=>'zero-swap/tail-'+i)]);
module.exports={defaults,finish,run};
