#!/usr/bin/env node
'use strict';
// Preserving entry to the four upper words. Cleanup is deliberately not
// implied: original lower u/q are still in the visible stack on return.
const probe=require('./k1-repack-deep-clone-probe.cjs');
const single=require('./k1-single-v-entry-check.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const brief=require('./k1-v-marker-probe.cjs').brief;
const defaults={...probe.defaults,...single.defaults,upperLeadPhase:1};
function finish(c,o={},record=()=>{}) {
  probe.finish(c,{...o,...single.defaults,afterClonePhase:2,
    afterClone:[['0'],['K','0'],['0'],['F',',']],
    afterCloneWaits:[8,10,8+(o.upperLeadPhase??1),8]},record);
  if(o.afterUpperPhase){record('after-upper-phase');c.runFrames(o.afterUpperPhase);}
  for(const [i,keys] of (o.afterUpper??[]).entries())
    stack.act(c,record,'after-upper-'+i,keys,o.afterUpperWaits?.[i]??8);
}
function run(o={}) {
  o={...defaults,...o};
  return cap.run(o,finish,['clone-prefix','clone-sign',
    ...Array.from({length:4},(_,i)=>'after-clone-'+i),
    ...(o.afterUpper??[]).map((_,i)=>'after-upper-'+i)]);
}
if(require.main===module) {
  const out=brief(run(JSON.parse(process.argv[2]||'{}')));
  out.rows=out.rows.filter(e=>e.stage.startsWith('after-')||e.stage==='done'||e.missing.length);
  out.routes=out.routes.filter(e=>e.stage.startsWith('after-'));
  console.log(JSON.stringify(out,null,2));
}
module.exports={defaults,finish,run};
