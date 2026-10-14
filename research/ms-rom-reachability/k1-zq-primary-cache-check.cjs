#!/usr/bin/env node
'use strict';
// Fresh keyboard preparation only. Cached state is inspected, never imported
// into a calculator; VP is then executed normally at the same native phase.
const assert=require('node:assert/strict');
const probe=require('./k1-zq-origin-entry.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');

function run() {
  const c=cap.prepare(probe.defaults),initial=fullMsPages(c);
  registers(c);program(c);aligned(c);probe.finish(c,probe.defaults);
  const beforeRing=peek(c),v=initial.V.slice(2),q=initial.Q.slice(2);
  assert.equal(raw(beforeRing.T),v);assert.equal(raw(beforeRing.P7),q);
  const buffers=[];
  for(const chip of ['ik1302','ik1303','ik1306'])for(const field of ['r','stack']) {
    const values=c[chip][field].slice(),lanes=[0,1,2].map(n=>raw(values,n));
    const complete=[];
    for(let offset=0;offset<42;offset++) {
      const word=Array.from({length:12},(_,j)=>values[(offset+3*(11-j))%42])
        .map(n=>n.toString(16).toUpperCase()).join('');
      if(word===v||word===q)complete.push({offset,source:word===v?'v':'q'});
    }
    assert.deepEqual(complete,[],chip+'.'+field+' has no complete cyclic v/q word');
    buffers.push({chip,field,values,lanes,complete});
  }
  const get=(chip,field,lane)=>buffers.find(x=>x.chip===chip&&x.field===field).lanes[lane];
  assert.equal(get('ik1302','r',1).slice(3),v.slice(3));
  assert.equal(get('ik1303','stack',1).slice(3),v.slice(3));
  assert.equal(get('ik1303','stack',2).slice(3),v.slice(3));
  assert.equal(get('ik1306','r',0).slice(0,3),v.slice(0,3));
  assert.equal(get('ik1306','r',1).slice(0,3),v.slice(0,3));
  stack.act(c,()=>{},'primary-vp',['ВП']);
  const afterRing=peek(c);
  assert.deepEqual(afterRing,beforeRing,'VP holds the complete 630-tetra ring on the base fixture');
  c.runFrames(3);
  assert.deepEqual(peek(c),beforeRing,'ring still held after three ordinary frames');
  return {v,q,buffers,vpHolds630RingTetras:true,
    nativeFixture:'base only',noGlobalInformationLossClaim:true};
}
if(require.main===module)console.log('PASS cache fragments and VP:',JSON.stringify(run(),null,2));
module.exports={run};
