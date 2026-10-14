#!/usr/bin/env node
'use strict';
// Old Z exit parks v in the visible stack and leaves U/V duplicates of u.
// The later clone is safe; NOP restores U, leaving real/Y/T/V markers.
// Two native fixtures audited; not a clean exit or a general numeric contract.
const z=require('./k1-z-reserve-restored.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...z.defaults,
  values:['-1.2345678E-42','-7.654321E-23','-9.8765432E-17','-1.2345678E-31'],
  deepLeadPhase:2,deepTail:[['K','0']],deepTailPhases:[1]};
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};
  z.finish(c,{...o,stopAfterUnmark:true,verifyExit:false},record);
  stack.act(c,record,'deep/prepare',['F',',']);
  for(const [i,k] of ['Сx','K','Сx','K','8'].entries())stack.act(c,record,'deep/marker-'+i,[k]);
  record('deep/phase');c.runFrames(o.deepLeadPhase);
  stack.act(c,record,'deep/clone',['↔']);
  for(const [i,keys] of o.deepTail.entries()) {
    record('deep/tail-phase-'+i);c.runFrames(o.deepTailPhases?.[i]??0);
    stack.act(c,record,'deep/tail-'+i,keys,o.deepTailWaits?.[i]??8);
  }
}
const run=(o={})=>frame.run({defaults,finish},o);
function traced(o={}) {
  o={...defaults,...o};
  return cap.run(o,finish,['clone-prefix','clone-sign','after-clone-0','rotate/reserve','rotate/tail-0',
    'deep/prepare','deep/clone',...[0,1,2,3,4].map(i=>'deep/marker-'+i),
    ...o.deepTail.map((_,i)=>'deep/tail-'+i)]);
}
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_Z_DEEP_OPTIONS||'{}')),lost=r.rows.find(x=>x.missing.length);
  console.log(JSON.stringify({options:r.options,firstLoss:lost?{stage:lost.stage,missing:lost.missing}:null,
    rows:r.rows.filter(x=>x.stage.startsWith('deep/')||x.stage==='immediate'||x.stage==='done'||x===lost)
      .map(({ring,registers,...x})=>({...x,p0:registers[0]}))},null,2));
}
module.exports={defaults,finish,run,traced};
