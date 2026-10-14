#!/usr/bin/env node
'use strict';
// Candidate: close the six-word cycle without changing the guarded Q.
// Execution order S; C^-1; (V Q); C gives (P0 P8 P7 W U).
// C=(P0 U V W). Native composition/return still requires testing.
const six=require('./k1-six-word-cycle.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const qswap=require('./k1-visible-q-swap.cjs');
const labels=['six','lower-inverse-0','lower-inverse-1','lower-inverse-2','vq','lower-forward'];
function lower(c,o={},record=()=>{}) {
  stack.act(c,record,'lower-load',['П→X','0']);
  stack.finish(c,{...o,phaseOffset:0},s=>record('lower/'+s));
  stack.act(c,record,'lower-store',['X→П','0']);
  stack.act(c,record,'lower-clear',['Сx','В↑','В↑','В↑','+']);
}
function finish(c,o={},record=()=>{}) {
  six.finish(c,{...o,clearByZero:false,returnedQ:false,alignScratchRetries:false},s=>record('six/'+s));
  const local={...o,phaseOffset:0};
  for(let i=0;i<3;i++)lower(c,local,s=>record('lower-inverse-'+i+'/'+s));
  qswap.finish(c,local,s=>record('vq/'+s));
  lower(c,local,s=>record('lower-forward/'+s));
}
module.exports={labels,lower,finish};
