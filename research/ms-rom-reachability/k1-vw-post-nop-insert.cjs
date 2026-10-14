#!/usr/bin/env node
'use strict';
// Bounded structural diagnostics: one numeric permutation between the NOP
// removal of W and the established removal/restoration tail. Not a K1 claim.
const nop=require('./k1-vw-nop-read.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const defaults={...nop.defaults,fullUpper:['-1E-99','-2E-50','9033','9044'],
  insertKeys:['↔'],insertPhase:0,cleanupPhase:0};
function finish(c,o={},record=()=>{}) {
  nop.finish(c,{...o,afterNop:[]},record);
  record('insert/phase');c.runFrames(o.insertPhase??0);
  stack.act(c,record,'insert/operation',o.insertKeys??['↔']);
  record('insert/cleanup-phase');c.runFrames(o.cleanupPhase??0);
  stack.act(c,record,'insert/clear-v',['K','×']);
  stack.act(c,record,'insert/clear-t',['0']);
  stack.push(c,s=>record('insert/restore-first/'+s));
  for(let i=0;i<2;i++)stack.act(c,record,'insert/rotate-'+i,['F',',']);
  stack.push(c,s=>record('insert/restore-second/'+s));
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','nop/read','insert/operation','insert/clear-v','insert/clear-t']);
const probe={defaults,finish,run};
function brief(r) {
  const relevant=r.rows.filter(x=>x.stage.startsWith('insert/')||x.stage==='done');
  const selected=relevant.filter(x=>['insert/operation','insert/clear-v','insert/clear-t',
    'insert/restore-first/push-marker-0','done'].includes(x.stage));
  return {options:r.options,firstLoss:r.rows.find(x=>x.missing.length),
    selected:selected.map(({ring,...row})=>row)};
}
if(require.main===module) {
  const r=frame.run(probe,JSON.parse(process.argv[2]||'{}'));
  const out=brief(r);if(out.firstLoss)delete out.firstLoss.ring;
  console.log(JSON.stringify(out));
}
module.exports={...probe,brief};
