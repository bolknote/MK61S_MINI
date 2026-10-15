#!/usr/bin/env node
'use strict';
// Deliberately discards the order carrier to study EXP on an isolated Ubad
// under the ordinary marker. This is NOT a preserving writer continuation.
const high=require('./k1-u-header-high-carrier.cjs');
const ready=require('./k1-high-carrier-ready-retry.cjs');
const {create}=require('./k1-writer-replay.cjs');
const isolate=[['align-isolate',[],2],['isolate-roll',['F',',']],
  ['isolate-lastx-f',['F']],['isolate-lastx',['В↑']],
  ['discard-header-carrier',['П→X','0']],['ubad-to-X',['↔']]];
function run(file){
  const s=create(file);
  for(const a of [...high.maker,...high.writer,...ready.retry,...isolate])s.advance(a,false);
  const isolated=s.state();
  if(isolated.markers.join()!=='marker'||isolated.visible.X!==isolated.banks[15])
    return{isolated,stopped:'ordinary-marker Ubad isolation contract failed'};
  const rows=[];
  for(const [label,keys] of [['exponent-zero',['ВП','0','K','0']],
    ['store-exponent-zero',['X→П','0','ВП','0','K','0']],
    ['abs-ubad',['K','4']],['negate-ubad',['/-/']]]){
    const b=create(file,s.core);b.advance([label,keys],true);const r=b.result();
    rows.push({label,end:r.end,paths:r.paths.filter(p=>['9c','a3','ee','e9','e7'].includes(p.ip)),
      firstProtectedChange:r.firstProtectedChange});
  }
  return{isolated,rows,boundary:'negative resource experiment: mH explicitly discarded; no all23 preservation/restoration claim'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={isolate,run};
