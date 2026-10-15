#!/usr/bin/env node
'use strict';
// Bring the reserved marker to X with controller-ready ROLLs. Then the known
// STORE/EXP (CF) digit replacement can remove the leading F without supplying
// U's original order from outside. Hypothesis only until native verification.
const high=require('./k1-u-header-high-carrier.cjs');
const ready=require('./k1-high-carrier-ready-retry.cjs');
const {create}=require('./k1-writer-replay.cjs');
const unpack=[['align-unpack',[],2],['roll-to-Z',['F',',']],['prepare-T-roll',['F',',']],
  ['roll-to-Y',['F',',']],['roll-to-X',['F',',']],['save-packed-header',['X→П','0']],
  ['replace-leading-F',['ВП']],['hold-unpacked-header',['K','0']]];
function operation(c,o,record=()=>{}){
  ready.operation(c,o,record);
  for(const [stage,keys,n=8] of unpack){record(stage);c.pressSequence(keys).runFrames(n);}
}
function run(file){
  const s=create(file);
  for(const a of [...high.maker,...high.writer,...ready.retry])s.advance(a,false);
  const expectedMarker={'roll-to-Z':'Z','prepare-T-roll':'Z','roll-to-Y':'Y','roll-to-X':'X'};
  for(const a of unpack){
    s.advance(a,true);
    const at=expectedMarker[a[0]];
    if(at&&!s.state().markers.includes(at))return{...s.result(),
      stopped:'Expected '+at+' marker did not survive '+a[0]+'; CF continuation not executed'};
  }
  return s.result();
}
if(require.main===module){const r=run(process.argv[2]);console.log(JSON.stringify({...r,
  stages:r.stages.slice(-unpack.length).map(s=>({stage:s.stage,end:s.end})),
  changes:r.changes.filter(c=>c.area==='Ms'),paths:r.paths.filter(p=>['9c','ee','e9','a3','e7'].includes(p.ip))}));}
module.exports={unpack,operation,run};
