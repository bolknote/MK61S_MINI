#!/usr/bin/env node
'use strict';
// Native candidate, not a promised exchange. Each transition is fixed-key.
const p=require('./k1-p0-carrier-probe.cjs');
const carrierActions=[['ВП'],['4'],['X→П','0'],['П→X','0'],
  ['F'],['В↑'],['F'],['В↑'],['K','X→П',',']];
function run(o={}) {return p.run({...o,carrierActions});}
function brief(r) {
  const b=p.brief(r);
  return {stages:b.stages,paths:b.paths,
    registers:r.afterRegisters.map((v,i)=>[i,r.beforeRegisters[i],v]).filter(x=>x[1]!==x[2]),
    ms:Object.entries(r.after).filter(([n,v])=>r.before[n]!==v),
    programHeld:JSON.stringify(r.afterProgram)===JSON.stringify(r.beforeProgram)};
}
if(require.main===module)console.log(JSON.stringify(brief(run()),null,2));
module.exports={carrierActions,run,brief};
