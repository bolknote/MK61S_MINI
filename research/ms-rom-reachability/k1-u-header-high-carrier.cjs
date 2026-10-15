#!/usr/bin/env node
'use strict';
// ROM-directed relocation of two positive-order digits into safe fields 5/6.
// A short Fxx carrier should avoid the long-carrier formatter's T write.
// lg/integer remains a selected-domain prototype, not a universal extractor.
const legacy=require('./k1-u-header-marker-plan.cjs');
const {create}=require('./k1-writer-replay.cjs');
const maker=legacy.actions.slice(0,legacy.actions.findIndex(a=>a[0]==='marker-exponent')+1)
  .map(([stage,keys])=>[stage,stage==='scale-constant'?[...'1000']:keys.slice()]);
const writer=[['save-carrier',['X→П','0']],['push-carrier',['П→X','0']],
  ['lastx-v-f',['F']],['lastx-v',['В↑']],['lastx-p-f',['F']],['lastx-p',['В↑']],
  ['indirect-p',['K','X→П',',']],['p-to-t-marker',['П→X','0']],['write-v',['↔']]];
const exit=[['drop-marker',['П→X','0']],['rotate-0',['F',',']],['rotate-1',['F',',']],
  ['rotate-2',['F',',']],['restore-v',['X→П','0']]];
function operation(c,o,record=()=>{}){
  require('./k1-zero-uv-retained-reader.cjs').operation(c,o,record);
  const actions=[...maker,...(o.stop==='maker'?[]:writer),...(o.stop==='exit'?exit:[])];
  for(const [stage,keys] of actions){record(stage);c.pressSequence(keys).runFrames(8);}
}
function run(file,stop='writer'){
  const s=create(file);
  for(const a of maker)s.advance(a,['marker-fraction','marker-exponent'].includes(a[0]));
  if(stop!=='maker')for(const a of writer)s.advance(a,true);
  if(stop==='exit')for(const a of exit)s.advance(a,true);
  const r=s.result();return{...r,expectedCarrier:'0040F'+s.d.metadata.originalWords[15].slice(1,3)+'00000',
    boundary:'new high-field automatic U-order carrier/writer hypothesis; not a full K1 or universal numeric proof'};
}
if(require.main===module){const r=run(process.argv[2],process.argv[3]);console.log(JSON.stringify({...r,
  stages:r.stages.map(s=>({stage:s.stage,startPhase:s.start.phase,end:s.end}))}));}
module.exports={maker,writer,exit,operation,run};
