#!/usr/bin/env node
'use strict';
// Candidate closed cycle: P0 -> P8 -> P7 -> Q -> W -> U -> P0.
// V stays fixed. This is NOT six inter-bank pairs or a whole-domain K1.
// The entry/cleanup currently needs a guarded numeric Q; test explicitly.
const prefix=require('./k1-two-hole-prefix.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
function finish(c,o={},record=()=>{}) {
  if(o.returnedQ&&!o.clearByZero)throw new Error('returnedQ requires the zero-based marker exit');
  prefix.finish(c,{...o,plantMarkerExponent:undefined,stopAfterGuard:false,signBuffer:false,
    alignScratchRetries:o.alignScratchRetries??!!o.returnedQ,
    zeroGuard:true,neutralPlantMarker:true,neutralPlantRefresh:true,
    clearBeforeSwap:true,swaps:0,tailWaits:[6],
    tail:[['F',','],['F',','],['K'],['5'],...(o.clearByZero?
      [['0'],['K','0'],['0']]:[['П→X','0'],['П→X','0']])]},record);
  // Only w remains uniquely visible; all other values already have stored
  // copies. Put w in X and use the retaining reader to return it into Ms.
  for(let i=0;i<3;i++)stack.act(c,record,'restore-w-rotate-'+i,['F',',']);
  stack.finish(c,{...o,phaseOffset:0},s=>record('restore-w/'+s));
  if(o.returnedQ) {
    // Research extension: W may contain q OR a duplicate v after SIGN's
    // late formatter. The retaining cycle returns old W=q in visible X.
    // Shift it back into U, discarding only a now-redundant q/v copy.
    // This changes the permutation; it is NOT the original six-cycle.
    stack.blindPush(c,{...o,phaseOffset:0},s=>record('return-q/'+s));
  }
  stack.act(c,record,'cycle-clear',['Сx','В↑','В↑','В↑','+']);
}
module.exports={finish};
