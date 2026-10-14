#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const pair=require('./k1-v-p0-pair.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function record(o={},operation=pair.finish) {
  const actions=[];let stage='';
  const methods={press(k){actions.push(['key',k,stage]);return this;},pressSequence:MK61.prototype.pressSequence,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n,stage]);return this;}};
  const c=new Proxy(methods,{get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden live read '+String(k));return t[k];},
    set(){assert.fail('forbidden live assignment');}});
  operation(c,o,s=>{stage=s;});return actions;
}
function compareUnobserved(expected,o={},operation=pair.finish) {
  const c=capture.prepare(o);fullMsPages(c);registers(c);program(c);aligned(c);
  operation(c,o);c.runFrames(3);aligned(c);fullMsPages(c);registers(c);program(c);
  assert.deepEqual(JSON.parse(JSON.stringify(c)),expected);
  return createHash('sha256').update(JSON.stringify(c)).digest('hex');
}
for(const [operation,o] of [[pair.finish,{}],[pair.roundTripFinish,{verifyExit:true}]]) {
  const actions=record(o,operation);
  assert.deepEqual(actions,record({...o,incoming:'not read',values:['not read'],fullUpper:['not read'],p3:'not read'},operation));
  const keys=actions.filter(a=>a[0]==='key').length;
  const frames=keys*2+actions.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0);
  if(operation===pair.finish){assert.equal(keys,57);assert.equal(frames,452);}
  console.log('PASS fixed keyboard pair surface:',JSON.stringify({roundTrip:operation===pair.roundTripFinish,keys,frames,noHiddenReads:true}));
}
module.exports={record,compareUnobserved};
