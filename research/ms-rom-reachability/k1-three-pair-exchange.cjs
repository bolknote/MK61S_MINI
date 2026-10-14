#!/usr/bin/env node
'use strict';
// Four C=(P3 U V W) cycles interleaved with ordinary P3/P2, P3/P1,
// P3/P0 transpositions. Native tests check three pair exchanges and P3
// restoration for declared short-number fixtures, not all numeric classes.
const assert=require('node:assert/strict');
const cycle=require('./k1-lower-stack-cycle.cjs');
function finish(c,o={},record=()=>{}) {
  assert.equal(o.settleFrames??8,8,'fixed timing contract');
  for(let i=0;i<4;i++) {
    if(i){record('pair-between-'+i);c.runFrames(1);}
    cycle.finish(c,{...o,hubKey:'3',phaseOffset:i?0:(o.phaseOffset??0)},s=>record('pair-cycle'+i+'/'+s));
    if(i===3)break;
    const target=['2','1','0'][i];
    for(const [j,keys] of [['П→X','3'],['П→X',target],['X→П','3'],['↔'],['X→П',target]].entries()) {
      record('pair-swap'+i+'/'+j);c.pressSequence(keys).runFrames(8);
    }
  }
}
function twice(c,o={},record=()=>{}) {
  finish(c,o,s=>record('first/'+s));
  record('pair-inverse-gap');c.runFrames(2);
  finish(c,{...o,phaseOffset:0},s=>record('second/'+s));
}
module.exports={finish,twice};
