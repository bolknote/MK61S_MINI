#!/usr/bin/env node
'use strict';
// Direct Q/P7 entry: remove the visible T marker before the first swap.
// The previous W/Q request could erase V in one phase. It is omitted here.
// Still an unfinished entry: hidden U marker and displaced words remain.
// NOT all-number safe: canonical Q=1 loses old P7 in the late formatter.
const prefix=require('./k1-two-hole-prefix.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
function finish(c,o={},record=()=>{}) {
  prefix.finish(c,{...o,stopAfterGuard:false,signBuffer:false,
    plantMarkerExponent:undefined,zeroGuard:true,clearBeforeSwap:true,swaps:0,
    tail:[['0'],['K','0'],['↔']]},record);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish,['tail-2']);
module.exports={finish,run};
