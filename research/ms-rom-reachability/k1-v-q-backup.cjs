#!/usr/bin/env node
'use strict';
// A different continuation before the upper request: ENTER backs W,
// then Last X reads Q. The late formatter must leave the new X alone.
const deep=require('./k1-repack-deep-clone-probe.cjs');
const single=require('./k1-single-v-entry-check.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...deep.defaults,...single.defaults,fullUpper:['-1E-99','9022','9033','9044']};
function finish(c,o={},record=()=>{}) {
  deep.finish(c,{...o,...single.defaults,afterClonePhase:2,
    afterClone:[['0'],['В↑'],['F','В↑']],afterCloneWaits:[11,8,8]},record);
  if(o.afterReservePhase){record('after-reserve-phase');c.runFrames(o.afterReservePhase);}
  for(const [i,keys] of (o.afterReserve??[]).entries())
    stack.act(c,record,'after-reserve-'+i,keys,o.afterReserveWaits?.[i]??8);
}
function run(o={}) {
  o={...defaults,...o};return cap.run(o,finish,['clone-prefix','clone-sign',
    ...Array.from({length:3},(_,i)=>'after-clone-'+i),
    ...(o.afterReserve??[]).map((_,i)=>'after-reserve-'+i)]);
}
if(require.main===module) {
  const out=require('./k1-v-marker-probe.cjs').brief(run(JSON.parse(process.argv[2]||'{}')));
  out.rows=out.rows.filter(e=>e.stage.startsWith('after-')||e.stage==='done'||e.missing.length);
  out.routes=out.routes.filter(e=>e.stage.startsWith('after-'));
  console.log(JSON.stringify(out,null,2));
}
module.exports={defaults,finish,run};
