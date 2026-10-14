#!/usr/bin/env node
'use strict';
// Partial preserving entry, not a completed permutation or a K1 command.
// Swap W/Q first, then remove U by two visible rotations. This keeps all
// four upper Ms words outside the scratch area and leaves p backed in X1.
const prefix=require('./k1-two-hole-prefix.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const hist=require('./k1-puhov-ring-probe.cjs');
const defaults={...hist.defaults,phaseOffset:1,
  values:['-1.2345678E-42','-7.654321E-23','-9.8765432E99','-12345678']};
function finish(c,o={},record=()=>{}) {
  prefix.finish(c,{...o,plantMarkerExponent:undefined,stopAfterGuard:false,signBuffer:false,
    alignScratchRetries:true,zeroGuard:true,neutralPlantMarker:true,neutralPlantRefresh:true,
    clearBeforeSwap:true,swaps:1,tailWaits:undefined,tail:[['F',','],['F',',']]},record);
  for(const [i,keys] of (o.after??[]).entries())stack.act(c,record,'after-'+i,keys);
}
function run(o={}) {
  o={...defaults,...o};
  return cap.run(o,finish,['clone-swap-0','tail-0','tail-1',
    ...(o.after??[]).map((_,i)=>'after-'+i)]);
}
module.exports={defaults,finish,run};
