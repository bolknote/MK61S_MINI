#!/usr/bin/env node
'use strict';
// A derived, fixed-key route: copy damaged U through LastX, then rotate it
// into the false control position instead of trying an incorrectly addressed
// STORE0. Every stage checks the explicit 23-word information reserve.
const assert=require('node:assert/strict');
const high=require('./k1-u-header-high-carrier.cjs');
const ready=require('./k1-high-carrier-ready-retry.cjs');
const {create}=require('./k1-writer-replay.cjs');
const actions=[['align-Z',[],2],['marker-to-Z',['F',',']],
  ['copy-damaged-U',['F','В↑']],['ready-U-to-T',['F',',']],
  ['long-unary-sqrt',['F','-']],
  ['marker-to-Y',['F',',']],['backup-v-in-T',['K','-']],
  ['long-unary-sqrt-v',['F','-']],['marker-to-X',['F',',']],
  ['save-packed-header',['X→П','0']],['replace-leading-F',['ВП']],
  ['hold-unpacked-header',['K','0']]];
const positive=actions.slice(0,actions.findIndex(a=>a[0]==='marker-to-Y')+1);
function operation(c,o,record=()=>{}){
  ready.operation(c,o,record);
  for(const [stage,keys,n=8] of positive){record(stage);c.pressSequence(keys).runFrames(n);}
}
function explicit(s,original){
  const t=s.state(),stored=[...t.banks,...Object.values(t.visible)],
    carrier=stored.find(w=>w==='0040F'+original[15].slice(1,3)+'00000'),
    tail=stored.find(w=>w.slice(3)===original[15].slice(3)),
    decoded=carrier&&tail?'0'+carrier.slice(5,7)+tail.slice(3):null;
  return{all23:original.every(w=>stored.includes(w)||w===decoded),carrier,decoded,
    missing:original.filter(w=>!stored.includes(w)&&w!==decoded)};
}
function run(file,stop='hold-unpacked-header',includeCore=false){
  assert.ok(actions.some(a=>a[0]===stop));const s=create(file);
  for(const a of [...high.maker,...high.writer,...ready.retry])s.advance(a,false);
  const startWords=s.result().words,original=s.d.metadata.originalWords,
    expected={ 'marker-to-Z':'Z','copy-damaged-U':'T','ready-U-to-T':'Z',
      'marker-to-Y':'Y','marker-to-X':'X'};
  const checkpoints=[];let stopped=null;
  for(const a of actions){
    s.advance(a,true);const e=explicit(s,original),state=s.state();
    checkpoints.push({stage:a[0],state,reserve:e});
    if(!e.all23){stopped='explicit original-word reserve failed after '+a[0];break;}
    if(expected[a[0]]&&!state.markers.includes(expected[a[0]])){
      stopped='expected '+expected[a[0]]+' marker absent after '+a[0];break;
    }
    if(a[0]===stop)break;
  }
  const r=s.result();assert.equal(r.firstProtectedChange,null);
  const out={...r,newSuffixWords:r.words-startWords,checkpoints,stopped,
    paths:r.paths.filter(p=>['9c','ee','e9','a3','e7','d4','d6'].includes(p.ip)),
    changes:r.changes.filter(c=>c.area==='Ms'||c.area==='register'),
    boundary:'guarded authentic detached fixed-key unpack continuation; not native U restoration or full K1'};
  return includeCore?{...out,core:s.core,d:s.d}:out;
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],process.argv[3])));
module.exports={actions,positive,operation,explicit,run};
