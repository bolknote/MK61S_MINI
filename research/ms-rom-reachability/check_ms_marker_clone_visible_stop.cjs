#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_marker_clone_visible_stop.cjs');
const {checkMirrored,guarded,release}=require('./check_ms_marker_clone_w.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {createHash}=require('node:crypto');
const marker='0000F0000000',zero='000000000000';
function check(r) {
  const out=checkMirrored({...r,options:{...r.options,sourceKey:'В↑',sourceMirror:'6'}});
  const {attempts,displays}=r.result;
  assert.ok(attempts>=1&&attempts<=3);assert.deepEqual(displays,[...Array(attempts-1).fill(','),'0,']);
  assert.equal(r.traced.display,'0,');assert.equal(out.entries.length,1);
  assert.equal(out.entries[0].stage,'clone-swap'+(attempts-1));
  const es=r.traced.events;
  for(let i=0;i<attempts;i++) {
    const at=es.find(e=>e.stage==='clone-swap'+i&&e.ring);assert.ok(at);
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(at.ring[n])),[marker,marker,zero,zero]);
    assert.equal(raw(at.ring.U),marker);assert.equal(raw(at.ring.W),r.before.V.slice(2));
  }
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[zero,marker,zero,zero]);
  return {...out,attempts,displays};
}
function main() {
  if(process.env.MS_CLONE_VISIBLE_UNOBSERVED) {
    const o=guarded({phaseOffset:1}),r=p.run(o);check(r);
    const expected=JSON.parse(JSON.stringify(r.calc)),expectedResult=structuredClone(r.result),expectedDigest=digest(r.calc);
    release(r);
    const c=p.prepare(o),result=p.finish(c,o);c.runFrames(3);aligned(c);
    assert.deepEqual(result,expectedResult);assert.deepEqual(JSON.parse(JSON.stringify(c)),expected);
    assert.equal(digest(c),expectedDigest);
    console.log('PASS adaptive observed/unobserved, every serialized data field:',
      createHash('sha256').update(JSON.stringify(c)).digest('hex'));return;
  }
  const cases=[guarded({}),guarded({phaseOffset:1}),guarded({phaseOffset:2}),
    guarded({phaseOffset:2,independentP8:'-8.7654321E-17',
      fullUpper:['-7.654321E23','-1E-99','8.7654321E-17','1.2345678E42']}),
    guarded({settleFrames:12,markerFrames:8})];
  const from=Number(process.env.MS_CLONE_VISIBLE_FROM??0),count=Number(process.env.MS_CLONE_VISIBLE_CASES??cases.length);
  for(const o of cases.slice(from,from+count)) {
    const r=p.run(o);console.log('PASS adaptive W clone:',JSON.stringify(o),JSON.stringify(check(r)));release(r);
  }
}
if(require.main===module)main();
module.exports={check};
