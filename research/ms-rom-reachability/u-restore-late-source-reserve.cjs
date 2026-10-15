#!/usr/bin/env node
'use strict';
// Two structurally derived reserve hypotheses at p/v/mZ/UbadT.
// A selected-domain integer sum is useful only if it survives in an explicit
// word; processor-cache coincidences do not establish preservation or a reader.
const high=require('./k1-u-header-high-carrier.cjs');
const ready=require('./k1-high-carrier-ready-retry.cjs');
const unpack=require('./u-restore-ready-unpack-route.cjs');
const {create}=require('./k1-writer-replay.cjs');
function run(file){
  const prefix=create(file);
  for(const a of [...high.maker,...high.writer,...ready.retry,...unpack.actions.slice(0,4)])prefix.advance(a,false);
  const results=[];
  for(const [stage,keys] of [['sum-p-v',['+']],['recall-p0',['П→X','0']],['product-p-v',['*']],['long-unary-sqrt',['F','-']]]){
    const s=create(file,prefix.core);s.advance([stage,keys],true);const r=s.result();
    results.push({stage,...r,reserve:unpack.explicit(s,s.d.metadata.originalWords),
      paths:r.paths.filter(p=>['9c','ee','e9','a3','e7','d4','d6'].includes(p.ip)),
      changes:r.changes.filter(c=>c.area==='Ms'||c.area==='register')});
  }
  return{start:prefix.state(),results,
    boundary:'two authentic detached fixed-key source-reserve hypotheses; neither a native protocol nor a general numeric proof'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run};
