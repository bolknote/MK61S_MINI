#!/usr/bin/env node
'use strict';
// Bounded native dataflow experiment: can Q be read while keeping both the
// displaced W and the incoming P0 in the visible stack? No success assumed.
const historical=require('./k1-puhov-ring-probe.cjs');
const capture=require('./k1-bank-v-capture.cjs');
function finish(c,o={},record=()=>{}) {
  historical.finish(c,{...o,rotate:false,readLifts:o.retainMsV?4:6,tail:[]},record);
  const act=(name,keys)=>{record(name);c.pressSequence(keys).runFrames(o.settleFrames??8);};
  const register=o.retainKey??'0';
  const actions=o.retainMsV?
    [['retain-v-swap',['↔']],['retain-v-rotate-a',['F',',']],['retain-v-rotate-b',['F',',']]]:
    [['retain-p0-a',['П→X',register]],['retain-p0-b',['П→X',register]],
      ['retain-rotate-a',['F',',']],['retain-rotate-b',['F',',']],['retain-swap',['↔']]];
  if(o.retainOnlyW) {
    // Keep the historical reader's duplicate W instead of inserting P0.
    // Match the original five actions' duration, without reading any state.
    record('retain-w-phase');
    c.runFrames(actions.length*(o.settleFrames??8)+2*actions.reduce((n,a)=>n+a[1].length,0));
  } else for(const [n,k] of actions)act(n,k);
  for(const [i,k] of ['Сx','K','Сx','K','8'].entries())act('q-marker-'+i,[k]);
  if(o.neutralMarker) {
    act('q-neutral-order-f',['ВП']);act('q-neutral-order-1',['1']);
  }
  if(o.markerDelayFrames) {record('q-marker-delay');c.runFrames(o.markerDelayFrames);}
  act('q-load',['П→X',o.sourceKey??'9']);
  act('q-enter',['В↑']);
  if(o.saveQ)act('q-store',['X→П',register]);
  for(const [i,k] of (o.tail??[]).entries())act('q-tail-'+i,k);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish);
if(require.main===module)console.log(JSON.stringify(historical.brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={finish,run};
