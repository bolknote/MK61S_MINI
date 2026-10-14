#!/usr/bin/env node
'use strict';
// Compose T=(P0 U)(P1 V)(P2 W), G=(V Q), A=(P1 P3).
// Execution order T,G,T,A,T,G gives all four lower inter-bank pairs.
// This is not an exchange with the upper four Ms words or full K1.
const triple=require('./k1-three-pair-exchange.cjs');
const qswap=require('./k1-visible-q-swap.cjs');
const labels=['triple-1','vq-1','triple-2','ordinary-1-3','triple-3','vq-2'];
function finish(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0,reader:'x1-retry'};
  for(const name of labels) {
    const rec=s=>record(name+'/'+s);
    if(name.startsWith('triple-'))triple.finish(c,local,rec);
    else if(name.startsWith('vq-'))qswap.finish(c,local,rec);
    else for(const [i,keys] of [['П→X','1'],['П→X','3'],['X→П','1'],['↔'],['X→П','3']].entries()) {
      rec(String(i));c.pressSequence(keys).runFrames(8);
    }
  }
}
function twice(c,o={},record=()=>{}) {
  finish(c,o,s=>record('first/'+s));
  // No reset, hidden alignment, or even an inter-call wait here.
  finish(c,{...o,phaseOffset:0},s=>record('second/'+s));
}
module.exports={labels,finish,twice};
