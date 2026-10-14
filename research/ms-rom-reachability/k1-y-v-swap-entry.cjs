#!/usr/bin/env node
'use strict';
// Rejected direct approach: phase 1 leaves Y/T but no V marker; phase 2
// clones the old X marker into V and late U, destroying the sole v.
// Changing u to class 4 does not help: the late reader carries m, not u.
// The Z-backed successor reserves v before this otherwise destructive step.
const deep=require('./k1-repack-deep-clone-probe.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const defaults={...deep.defaults,clonePrefix:[],cloneKeys:['↔'],clonePhase:1,
  values:['-1.2345678E-42','-7.654321E-23','-9.8765432E-17','-1.234E42']};
const finish=(c,o={},record=()=>{})=>deep.finish(c,{...defaults,...o},record);
const run=(o={})=>frame.run({defaults,finish},o);
const traced=(o={})=>deep.run({...defaults,...o});
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_Y_V_SWAP_OPTIONS||'{}'));
  const lost=r.rows.find(x=>x.missing.length);
  console.log(JSON.stringify({options:r.options,firstLoss:lost?{stage:lost.stage,missing:lost.missing}:null,
    rows:r.rows.filter(x=>x.stage==='clone-sign'||x.stage.startsWith('after-clone')||
      x.stage==='immediate'||x.stage==='done'||x===lost).map(({ring,...x})=>x)},null,2));
}
module.exports={defaults,finish,run,traced};
