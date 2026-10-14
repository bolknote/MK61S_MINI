#!/usr/bin/env node
'use strict';
// Continuous invocations of the closed upper permutation. A nonzero
// betweenFrames is an explicit fixed timing control, not hidden alignment.
const close=require('./k1-zero-rotate-stack-close.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...close.defaults,verifyExit:false,rounds:2,betweenFrames:0};
function finish(c,o={},record=()=>{}) {
  try {
    for(let i=0;i<(o.rounds??2);i++) {
      if(i&&(o.betweenFrames??0)) {
        record('repeat/'+i+'/wait');c.runFrames(o.betweenFrames);
      }
      record('repeat/'+i+'/start');
      close.finish(c,{...o,verifyExit:false},s=>{
        if(i&&o.longGuardBeforeRepeatRotate&&s==='entry/tail-0') {
          // Diagnostic attempt, not a proven repair. The old X is also in
          // W at the audited entry. 9 keys plus 9 idle frames = 27 frames,
          // preserving the three-frame residue without hidden alignment.
          record('repeat/'+i+'/long-guard');
          c.pressSequence(['Сx',...'11111111']).runFrames(9);
        }
        record('repeat/'+i+'/'+s);
      });
      record('repeat/'+i+'/end');
    }
    return {failure:null};
  } catch(error) {
    record('repeat/aborted');
    return {failure:{name:error.name,message:error.message}};
  }
}
function run(o={}) {
  let outcome;
  const wrapped={defaults,finish(c,options,record){outcome=finish(c,options,record);}};
  return {...frame.run(wrapped,o),...outcome};
}
function traced(o={},extraStages=[]) {
  o={...defaults,...o};let outcome;
  const stages=Array.from({length:o.rounds},(_,i)=>[
    'clone-prefix','clone-sign','after-clone-0',...[0,1,2,3].map(j=>'u-reserve/tail-'+j),
    ...close.stages,...extraStages].map(s=>'repeat/'+i+'/'+s)).flat();
  const r=cap.run(o,(c,options,record)=>{outcome=finish(c,options,record);},stages);
  return {...r,...outcome};
}
module.exports={defaults,finish,run,traced};
