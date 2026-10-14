#!/usr/bin/env node
'use strict';
// Structural candidate: G; C^2; B, where G is the previously checked
// two-stage composition, C=(P0 U V W), and B is its second entry only.
// Do not infer native numeric/timing validity from these permutations.
const prior=require('./k1-repeat-entry-adapter.cjs');
const {lower}=require('./k1-guarded-upper-cycle.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...prior.closedDefaults,verifyExit:false,lowerRounds:2,thirdPhase:0};
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};
  prior.finish(c,{...o,verifyExit:false},s=>record('previous/'+s));
  for(let i=0;i<o.lowerRounds;i++) {
    record('lower/'+i+'/start');lower(c,{...o,phaseOffset:0},s=>record('lower/'+i+'/'+s));
  }
  record('third/phase');c.runFrames(o.thirdPhase);
  prior.second(c,o,s=>record('third/'+s));
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.pressSequence(['Сx']).runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
const run=(o={})=>frame.run({defaults,finish},o);
function traced(o={},stages=[]) {
  o={...defaults,...o};
  return cap.run(o,finish,[
    ...prior.nativeStages(o).map(s=>'previous/'+s),
    ...['adapter/0','second/entry/clone-swap-0','second/entry/tail-0','second/entry/tail-1',
      'exit/0','exit/1','exit/push/blind-duplicate','exit/push/push',
      'exit/push/push-clear','exit/push/push-return'].map(s=>'third/'+s),
    ...Array.from({length:o.lowerRounds},(_,i)=>'lower/'+i+'/lower/push'),...stages]);
}
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_THIRD_ENTRY_OPTIONS||'{}'));
  const loss=r.rows.findIndex(x=>x.missing.length);
  const picked=r.rows.filter(x=>/^(?:lower\/\d\/start|third\/phase|third\/adapter\/0|third\/second\/entry\/tail-|third\/exit\/|post\/|immediate|done)/.test(x.stage));
  console.log(JSON.stringify({options:r.options,firstLoss:loss<0?null:r.rows[loss].stage,
    rows:(loss<0?picked:[r.rows[loss-1],r.rows[loss],...picked.slice(-3)])
      .map(({ring,...x})=>x)},null,2));
}
module.exports={defaults,finish,run,traced};
