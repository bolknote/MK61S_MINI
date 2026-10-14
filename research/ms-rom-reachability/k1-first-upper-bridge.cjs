#!/usr/bin/env node
'use strict';
// Conditional first-upper bridge. Retains originals, but leaves a false U
// marker, working lower Ms and two originals only in Z/T. NOT a full pair.
const prefix=require('./k1-two-hole-prefix.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
function finish(c,o={},record=()=>{}) {
  prefix.finish(c,{...o,stopAfterGuard:false,signBuffer:false,
    zeroGuard:true,clearBeforeSwap:true,swaps:1,tail:[['0'],['K','0'],['↔']]},record);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish,['tail-2']);
module.exports={finish,run};
