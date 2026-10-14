#!/usr/bin/env node
'use strict';
// Structural candidate: use the lower T/U/V/W pushes to move and discard
// the surviving V marker after an already preserving upper rotation.
// Neither the classic marker factory nor its exit is assumed compatible.
const upper=require('./k1-preserving-upper-rotation.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const defaults={...upper.defaults,exitLeadPhase:0};
function finish(c,o={},record=()=>{}) {
  upper.finish(c,{...o,afterUpper:[],afterUpperPhase:0},record);
  record('lower-exit/phase');c.runFrames(o.exitLeadPhase??0);
  stack.push(c,s=>record('lower-exit/first/'+s));
  for(let i=0;i<2;i++)stack.act(c,record,'lower-exit/rotate-'+i,['F',',']);
  stack.push(c,s=>record('lower-exit/second/'+s));
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign',...Array.from({length:4},(_,i)=>'after-clone-'+i),
    ...['first','second'].flatMap(s=>['push','push-clear','push-return'].map(t=>'lower-exit/'+s+'/'+t))]);
const probe={defaults,finish,run};
if(require.main===module) {
  const r=frame.run(probe,JSON.parse(process.argv[2]||'{}'));
  const bad=r.rows.find(e=>e.missing.length);
  const selected=r.rows.filter(e=>e.stage==='lower-exit/phase'||e.stage.endsWith('/push')||
    e.stage.endsWith('/push-clear')||e.stage==='done');
  console.log(JSON.stringify({firstLoss:bad&&(({ring,...row})=>row)(bad),
    rows:selected.map(({ring,...row})=>row)}));
}
module.exports=probe;
