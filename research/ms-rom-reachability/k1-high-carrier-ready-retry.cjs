#!/usr/bin/env node
'use strict';
// First rejected request changes U to 1Fd. 9C can accept that reply; the
// second request must start at the original T-first ring scan, not real-marker
// first. Two FIXED frames restore the first request's phase (0 -> 168).
const high=require('./k1-u-header-high-carrier.cjs');
const {create}=require('./k1-writer-replay.cjs');
const retry=[['align-ready-request',[],2],['write-v-ready',['↔'],8]];
function operation(c,o,record=()=>{}){
  high.operation(c,{...o,stop:'writer'},record);
  for(const [stage,keys,frames] of retry){record(stage);c.pressSequence(keys).runFrames(frames);}
}
function run(file){
  const s=create(file);
  for(const a of high.maker)s.advance(a,false);
  for(const a of high.writer)s.advance(a,a[0]==='write-v');
  for(const a of retry)s.advance(a,true);
  const r=s.result();return{...r,oldP0InV:r.end.banks[16]===s.d.metadata.originalWords[0],
    boundary:'fixed phase-restored ready-U retry, detached original five-chip model; U header reserve/restore is still a separate obligation'};
}
if(require.main===module){const r=run(process.argv[2]);console.log(JSON.stringify({...r,
  stages:r.stages.slice(-3),changes:r.changes.filter(c=>c.area==='Ms'),
  paths:r.paths.filter(p=>p.stage==='write-v-ready'&&["9c","ee","e9","a3","e7"].includes(p.ip))}));}
module.exports={retry,operation,run};
