#!/usr/bin/env node
'use strict';
// A tempting literal replacement is not equivalent to the reciprocal exit.
// Recorded frame boundaries only; not a whole-state information-loss proof.
const assert=require('node:assert/strict');
const transfer=require('./k1-zv-comma-transfer.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
function finish(c,o,record) {
  transfer.finish(c,o,record);
  for(const [i,k] of ['Сx','1',','].entries()) {record('input/'+i);c.press(k);}
  c.runFrames(8);
}
function check() {
  const r=frame.run({defaults:transfer.defaults,finish}),at=s=>r.rows.find(e=>e.stage===s);
  const v=r.before.V.slice(2),a=r.before.P7.slice(2),u=r.before.U.slice(2),m='9990FFFFFFF0';
  assert.deepEqual(at('input/0').missing,[]);assert.deepEqual(at('input/1').missing,[]);
  assert.deepEqual(['X','Y','Z','T'].map(n=>at('input/1').values[n]),['000000000000',u,m,v]);
  assert.deepEqual(at('input/2').missing,[v]);
  assert.deepEqual(['X','Y','Z','T'].map(n=>at('input/2').values[n]),['000010000000','000000000000',u,m]);
  for(const stage of ['immediate','done']) {
    assert.deepEqual(at(stage).missing,[v,a]);assert.equal(at(stage).values.W,'000010000000');
  }
  const original=snapshotFromRing(r.initial);
  for(const e of r.rows) {
    const s=snapshotFromRing(e.ring);assert.deepEqual(s.program,original.program);
    assert.deepEqual(s.services,original.services);assert.deepEqual(s.words.slice(1,15),original.words.slice(1,15));
    assert.deepEqual(s.words.slice(20),original.words.slice(20));
  }
  return {literalPrefix:['Сx','1',','],CxHoldsAll23:true,firstDigitLosesWholeVFromTrackedWords:true,
    commaLosesWholeAFromTrackedWords:true,fullStateCollisionProved:false,reciprocalRouteUnaffected:true};
}
if(require.main===module)console.log('PASS rejected literal:',JSON.stringify(check()));
module.exports={finish,check};
