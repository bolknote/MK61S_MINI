#!/usr/bin/env node
'use strict';
// Bounded native experiments, not a closed exit or whole-domain K1.
// Every case starts again from the public keyboard fixture. The fast reader
// is passive; there is no cloned/imported state or live machine mutation.
const assert=require('node:assert/strict');
const frame=require('./k1-frame-boundary-probe.cjs');
const upper=require('./k1-preserving-upper-rotation.cjs');
const deep=require('./k1-repack-deep-clone-probe.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const swapped={defaults:deep.defaults,finish(c,o,record=()=>{}) {
  deep.finish(c,o,stage=>{
    if(stage==='marker-0') {
      // Conjugation of X/Y swap by visible rotations: exchange Y and Z.
      for(const [i,keys] of [['F',','],['↔'],['F',','],['F',','],['F',',']].entries())
        stack.act(c,record,'yz-swap-'+i,keys);
      record('yz-swap-phase');c.runFrames(2);
    }
    record(stage);
  });
}};
const cases={
  'not-reserve':{probe:upper,options:{afterUpperPhase:1,afterUpper:[['K','Сx']]}},
  'not-fraction':{probe:upper,options:{afterUpperPhase:1,afterUpper:[['K','Сx'],['K','8']]}},
  'not-enter-negative':{probe:upper,options:{afterUpperPhase:1,
    afterUpper:[['K','Сx'],['В↑'],['K','8']],afterUpperWaits:[8,10,8]}},
  'q-reserve':{probe:deep,options:{clonePhase:2}},
  'q-lastx-negative':{probe:deep,options:{clonePhase:2,afterClone:[['F','В↑']]}},
  'q-rotate-negative':{probe:deep,options:{clonePrefix:['F'],cloneKeys:[','],clonePhase:2}},
  'swapped-v':{probe:swapped,options:{clonePrefix:['F'],cloneKeys:[','],clonePhase:2}},
  'fraction-clone-negative':{probe:deep,options:{clonePhase:1,cloneKeys:['8']}},
  'abs-clone-negative':{probe:deep,options:{clonePhase:1,cloneKeys:['4']}},
};
function run(name,options={}) {
  assert.ok(Object.hasOwn(cases,name),'known structural experiment');
  const spec=cases[name];
  return frame.run(spec.probe,{...spec.options,...options});
}
function check(name,r) {
  const end=r.rows.at(-1),before=r.rows.find(x=>x.stage==='after-upper-0');
  if(name==='not-reserve') {
    assert.ok(before);
    assert.equal(end.values.X1,before.values.P7);
    for(const n of ['P7','P8','P9','P10','U','V','Q','Y','Z','T'])
      assert.equal(end.values[n],before.values[n],n+' endpoint held');
    assert.deepEqual(end.registers,before.registers);
    assert.deepEqual(end.missing,[]);
  } else if(name==='not-fraction') {
    assert.equal(end.values.X1,before.values.P7);
    assert.equal(end.values.X,before.values.P7);
    assert.equal(end.values.P7,'000000000000');
    assert.deepEqual(end.missing,[]);
  } else if(name==='not-enter-negative') {
    assert.deepEqual(end.missing,[before.values.T]);
  } else if(name==='q-reserve') {
    const start=r.rows.find(x=>x.stage==='clone-sign');
    assert.equal(end.values.X1,start.values.Z);
    for(const n of ['P7','P8','P9','P10','U','V','W','Q','X','Z','T'])
      assert.equal(end.values[n],start.values[n],n+' endpoint held');
    assert.deepEqual(end.missing,[]);
  } else if(name==='q-lastx-negative') {
    const start=r.rows.find(x=>x.stage==='clone-sign');
    assert.deepEqual(end.missing,[start.values.U]);
    assert.equal(end.values.X1,start.values.Z);
  } else if(name==='q-rotate-negative') {
    const start=r.rows.find(x=>x.stage==='clone-sign');
    assert.deepEqual(end.missing,[start.values.V]);
    assert.equal(end.values.X1,start.values.Z);
  } else if(name==='swapped-v') {
    const start=r.rows.find(x=>x.stage==='clone-sign');
    assert.equal(end.values.X,start.values.W);
    assert.equal(end.values.Y,start.values.V);
    assert.equal(end.values.X1,'00008FFFFFFF');
    for(const n of ['P7','P8','P9','P10','U','W','Q'])
      assert.equal(end.values[n],start.values[n],n+' endpoint held');
    for(const n of ['Z','T','V'])assert.equal(end.values[n],'9990FFFFFFF0');
    assert.deepEqual(end.missing,[]);
  } else if(name==='fraction-clone-negative'||name==='abs-clone-negative') {
    const start=r.rows.find(x=>x.stage==='clone-sign');
    assert.deepEqual(end.missing,[start.values.V,
      ...(name==='abs-clone-negative'?[start.values.P7]:[])]);
  }
  return {name,boundaries:r.rows.length,endpointMissing:end.missing,
    boundaryPreservationOnly:true,normalExit:false,fullK1:false};
}
if(require.main===module) {
  const name=process.argv[2]??'not-reserve';
  const r=run(name,JSON.parse(process.argv[3]??'{}'));
  console.log(JSON.stringify({check:check(name,r),rows:frame.brief(r).rows.filter(x=>
    x.stage==='clone-sign'||x.stage.startsWith('after-upper')||
    x.stage.startsWith('after-clone')||x.stage==='done')},null,2));
}
module.exports={cases,swapped,run,check};
