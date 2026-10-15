#!/usr/bin/env node
'use strict';
// One derived cached-CF hypothesis: inspect the authentic post-ROL cache,
// then exactly EXP/NOP. Cached bits alone are never counted as a recoverer.
const assert=require('node:assert/strict');
const high=require('./k1-u-header-high-carrier.cjs');
const ready=require('./k1-high-carrier-ready-retry.cjs');
const unpack=require('./u-restore-ready-unpack-route.cjs');
const {create}=require('./k1-writer-replay.cjs');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
function caches(core){
  const out=[];
  for(const chip of ['ik1302','ik1303','ik1306'])for(const a of ['r','st'])for(let lane=0;lane<3;lane++){
    const digits=Array.from({length:14},(_,j)=>core.chips[chip][a][3*j+lane]),
      raw=digits.slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join(''),
      full=digits.slice().reverse().map(n=>n.toString(16).toUpperCase()).join('');
    out.push({chip,array:a,lane,raw,full});
  }
  return out;
}
function run(file){
  const s=create(file);
  for(const a of [...high.maker,...high.writer,...ready.retry,...unpack.positive])s.advance(a,false);
  const positive=s.state(),snapshots=[{stage:'positive-Y',state:positive,caches:caches(s.core)}],
    startWords=s.result().words;
  const unobserved=create(file,s.core),suffix=[['late-E7-barrier',['F',',']],
    ['immediate-EXP',['ВП']],['hold-CF',['K','0']]];
  const calls=[],originalStep=model.step;let stage=null,suffixWord=0;
  model.step=(core,pins)=>{
    const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
    if([0xCF,0xC3,0xC2,0xDC,0xDE,0xD4,0xD6,0xE7,0x34].includes(ip)&&calls.length<128)
      calls.push({stage,suffixWord,ip:ip.toString(16).toUpperCase(),s1:p.s1,
        lanes:caches(core).filter(c=>c.chip==='ik1302')});
    suffixWord++;return originalStep(core,pins);
  };
  try{
    for(const a of suffix){
      stage=a[0];s.advance(a,true);snapshots.push({stage,state:s.state(),caches:caches(s.core)});
    }
  }finally{model.step=originalStep;}
  for(const a of suffix)unobserved.advance(a,false);
  assert.deepEqual(s.core,unobserved.core,'passive cache/CF observer cannot affect the detached result');
  const r=s.result();assert.equal(r.firstProtectedChange,null);
  const all=[...r.end.banks,...Object.values(r.end.visible),...snapshots.at(-1).caches.map(c=>c.raw)];
  const cf=calls.filter(c=>c.stage==='immediate-EXP'&&c.ip==='CF');
  assert.equal(cf.length,1);
  assert.equal(cf[0].lanes.find(c=>c.array==='r'&&c.lane===1).raw,s.d.metadata.originalWords[16],
    'EXP uses the current v source B, not the IK1306 marker residue');
  assert.ok(calls.some(c=>c.stage==='immediate-EXP'&&c.ip==='C2'));
  assert.ok(!calls.some(c=>c.stage==='immediate-EXP'&&c.ip==='C3'));
  const residue=snapshots.at(-1).caches.find(c=>c.chip==='ik1306'&&c.array==='st'&&c.lane===1).raw;
  assert.equal(residue.slice(3),'0F'+s.d.metadata.originalWords[15].slice(1,3)+'00000',
    'the order digits remain passively visible in IK1306 ST lane1');
  assert.ok(!all.includes('003012000000'),'this particular cache-CF test does not unpack 1200');
  return{...r,snapshots,calls,newSuffixWords:r.words-startWords,
    detachedObserverMirror:true,
    headerWord1200Present:all.includes('003012000000'),
    paths:r.paths.filter(p=>['ee','e9','a3','e7'].includes(p.ip)),
    boundary:'one authentic detached cached-CF test; cache coincidence is not a working readout, all23 preservation or native success'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run,caches};
