#!/usr/bin/env node
'use strict';
// Candidate after returning the formatter-dependent duplicate:
// S=(P0 P8 P7 Q U)(V W). Execute S; C; (V Q); C^-1, C=(P0 U V W).
// Result (P0 P8 P7 U)(V W), so Q is fixed and four invocations are identity.
// This algebra is not a native numeric/timing contract by itself.
// NEGATIVE CONTROL: without aligning scratch-reader retries, the wide
// four-invocation test changes P9 during round 4. The aligned revision
// passes the documented wide phase-1 test, including an observer-free
// replay. This is still not a whole-domain or arbitrary-timing theorem.
const six=require('./k1-six-word-cycle.cjs');
const {lower}=require('./k1-guarded-upper-cycle.cjs');
const qswap=require('./k1-visible-q-swap.cjs');
const labels=['six','lower-forward','vq','lower-inverse-0','lower-inverse-1','lower-inverse-2'];
function finish(c,o={},record=()=>{}) {
  six.finish(c,{...o,clearByZero:true,returnedQ:true},s=>record('six/'+s));
  const local={...o,phaseOffset:0};
  lower(c,local,s=>record('lower-forward/'+s));
  qswap.finish(c,local,s=>record('vq/'+s));
  for(let i=0;i<3;i++)lower(c,local,s=>record('lower-inverse-'+i+'/'+s));
  // The new tail is 140 frames longer than S; this fixed pad restores the
  // previous residue modulo three, for the declared successful attempts.
  record('guarded-phase');c.runFrames(1);
}
module.exports={labels,finish};
