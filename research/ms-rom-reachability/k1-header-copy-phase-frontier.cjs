#!/usr/bin/env node
'use strict';
// Structural three-frame period analysis of one direct STORE, not a key search.
// A new empty X marker may make EE read the still-full T marker into spare P0.
const high=require('./k1-u-header-high-carrier.cjs'),ready=require('./k1-high-carrier-ready-retry.cjs');
const {create}=require('./k1-writer-replay.cjs');
const prepare=[['align-empty-marker',[],2],
  ...['Сx','K','-','ВП','K','0'].map((k,i)=>['empty-marker-'+i,[k],12])];
function run(file){
  const s=create(file);
  for(const a of [...high.maker,...high.writer,...ready.retry])s.advance(a,false);
  const before=s.state();for(const a of prepare)s.advance(a,true);
  const base=s.state(),phases=[];
  if(base.visible.X!=='0000F0000000')return{before,base,
    prepareStages:s.result().stages.slice(-prepare.length),protected:s.result().firstProtectedChange,
    phases,stopped:'Empty X marker was not made in the live T-marker context; do not STORE under a false premise',
    boundary:'negative detached marker-maker test; this is not a header-copy reachability or impossibility proof'};
  for(let frames=0;frames<3;frames++){
    const branch=create(file,s.core);branch.advance(['fixed-phase',[],frames],false);
    branch.advance(['copy-T-header',['X→П','0']],true);const r=branch.result();
    phases.push({frames,end:r.end,firstProtectedChange:r.firstProtectedChange,
      reads:r.paths.filter(p=>['ee','d4','9c'].includes(p.ip)),
      copiedFullHeader:r.end.banks[0]===before.visible.T});
  }
  return{before,base,prepareStages:s.result().stages.slice(-prepare.length),
    protected:s.result().firstProtectedChange,phases,
    boundary:'detached one-STORE scan frontier across the exact three frame residues; no native header-copy success'};
}
if(require.main===module){const r=run(process.argv[2]);console.log(JSON.stringify({...r,prepareStages:r.prepareStages.map(s=>({stage:s.stage,end:s.end.visible}))}));}
module.exports={prepare,run};
