#!/usr/bin/env node
'use strict';
// Keyboard adapters for a different second entry. closedDefaults has a
// two-fixture native audit; other options remain diagnostic. No full K1,
// arbitrary-repeat claim, state restoration, or hidden-state branch.
const close=require('./k1-zero-rotate-stack-close.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...close.defaults,verifyExit:false,betweenFrames:1,
  adapterStage:'entry/tail-0',adapterPhase:0,adapterActions:[],
  stopAt:'entry/after-0',exitActions:[]};
// One upper rotation supplies a long X for the original two visible
// rotations. After a Y-marker swap, the ordinary swap and lower push
// should store the remaining visible p, displacing only a duplicate.
// The companion checker validates this composition on its stated fixtures.
const closedDefaults={...defaults,adapterPhase:2,
  adapterActions:[{keys:['F',','],wait:9}],
  exitActions:[{keys:['↔']},{keys:['↔']}],lowerPush:true};
function second(c,o={},record=()=>{}) {
  o={...defaults,...o};
  const stop=Symbol('diagnostic endpoint');
  try {
    close.finish(c,{...o,verifyExit:false},s=>{
      if(s===o.adapterStage) {
        if(o.adapterPhase){record('adapter/phase');c.runFrames(o.adapterPhase);}
        for(const [i,action] of o.adapterActions.entries()) {
          record('adapter/'+i);
          c.pressSequence(action.keys).runFrames(action.wait??8);
        }
      }
      record('second/'+s);
      if(s===o.stopAt)throw stop;
    });
  } catch(e) {if(e!==stop)throw e;}
  for(const [i,action] of o.exitActions.entries()) {
    if(action.phase){record('exit/'+i+'/phase');c.runFrames(action.phase);}
    record('exit/'+i);c.pressSequence(action.keys).runFrames(action.wait??8);
  }
  if(o.lowerPush)stack.blindPush(c,o,s=>record('exit/push/'+s));
}
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};
  close.finish(c,{...o,verifyExit:false},s=>record('first/'+s));
  record('between');c.runFrames(o.betweenFrames);
  second(c,o,record);
  if(o.verifyExit) {
    record('post/manual');c.pressSequence(['Сx','2','В↑','3','+']).runFrames(8);
    record('post/zero');c.pressSequence(['Сx']).runFrames(8);
    record('post/program');c.pressSequence(['В/О','С/П']).runFrames(12);
  }
}
function run(o={}) {return frame.run({defaults,finish},o);}
function nativeStages(o={}) {
  return [
    ...['first','second'].flatMap(p=>['entry/clone-swap-0','entry/tail-0','entry/tail-1',
      'clone-prefix','clone-sign','after-clone-0',
      ...[0,1,2,3].map(i=>'u-reserve/tail-'+i),
      ...close.stages].map(s=>p+'/'+s)),
    ...Array.from({length:o.adapterActions?.length??0},(_,i)=>'adapter/'+i),
    ...Array.from({length:o.exitActions?.length??0},(_,i)=>'exit/'+i),
    ...['blind-duplicate','push','push-clear','push-return'].map(s=>'exit/push/'+s)];
}
function traced(o={},stages=[]) {
  return cap.run({...defaults,...o},finish,[...nativeStages(o),...stages]);
}
if(require.main===module) {
  const r=run({... (process.env.K1_REPEAT_ADAPTER_CLOSE?closedDefaults:{}),
    ...JSON.parse(process.env.K1_REPEAT_ADAPTER_OPTIONS||'{}')});
  console.log(JSON.stringify({options:r.options,
    rows:r.rows.filter(x=>['second/entry/plant-u','second/entry/clear-before-swap',
      'second/entry/clone-swap-0','second/entry/tail-0','second/entry/tail-1',
      'second/entry/after-0','immediate','done'].includes(x.stage)||x.stage.startsWith('adapter/')||x.stage.startsWith('exit/'))
      .map(({stage,phase,values,missing,registers})=>({stage,phase,values,missing,p0:registers[0]})),
    firstLoss:r.rows.find(x=>x.missing.length)?.stage??null},null,2));
}
module.exports={defaults,closedDefaults,second,finish,run,nativeStages,traced};
