#!/usr/bin/env node
'use strict';
// Detached, guarded continuation only. Back up the corrupted but control-ready
// U before trying to move the exponent carrier. No native state imports.
const assert=require('node:assert/strict');
const high=require('./k1-u-header-high-carrier.cjs');
const ready=require('./k1-high-carrier-ready-retry.cjs');
const {create}=require('./k1-writer-replay.cjs');
const route=[['align-first-roll',[],2],['marker-to-Z',['F',',']],
  ['get-u-f',['F']],['get-u',['В↑']],['align-u-store',[],1],['backup-u-P0',['X→П','0']],
  ['marker-to-Z-again',['F',',']],
  ['ready-marker-to-Y',['F',',']],['ready-marker-to-X',['F',',']],
  ['save-header',['X→П','0']],['unpack-header',['ВП']],['hold-header',['K','0']]];
function run(file){
  const s=create(file);
  for(const a of [...high.maker,...high.writer,...ready.retry])s.advance(a,false);
  const start=s.state(),uBad=start.banks[15],m=start.visible.T,p=start.banks[0],v=start.visible.Z;
  const checks={
    'marker-to-Z':q=>q.visible.Z===m&&q.visible.X===p&&q.visible.Y===v,
    'get-u':q=>q.visible.X===uBad&&q.visible.Y===p&&q.visible.Z===v&&q.visible.T===m,
    'backup-u-P0':q=>q.banks[0]===uBad&&q.banks[16]===p&&q.visible.T===m,
    'marker-to-Z-again':q=>q.visible.Z===m&&q.visible.T===uBad&&q.banks[16]===uBad,
    'ready-marker-to-Y':q=>q.visible.Y===m&&q.visible.Z===uBad&&q.visible.X===v,
    'ready-marker-to-X':q=>q.visible.X===m&&q.visible.Y===uBad
  };
  let stopped=null;
  for(const a of route){
    s.advance(a,true);
    if(s.result().firstProtectedChange){stopped='protected emitted field changed at '+a[0];break;}
    if(checks[a[0]]&&!checks[a[0]](s.state())){stopped='entry contract failed at '+a[0]+'; following actions not executed';break;}
  }
  return{...s.result(),stopped,initialReady:start,
    boundary:'guarded detached U backup/unpack hypothesis, never a native restoration claim'};
}
if(require.main===module){const r=run(process.argv[2]);console.log(JSON.stringify({...r,
  stages:r.stages.slice(-route.length).map(s=>({stage:s.stage,end:s.end})),
  paths:r.paths.filter(p=>['9c','ee','e9','e7','a3'].includes(p.ip)),
  changes:r.changes.filter(c=>c.area==='Ms')}));}
module.exports={route,run};
