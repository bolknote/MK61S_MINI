#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const maker=require('./k1-logical-carrier-maker.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function record(o={}) {
  const actions=[];let stage='';
  const methods={press(k){actions.push(['key',k,stage]);return this;},pressSequence:MK61.prototype.pressSequence,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n,stage]);return this;}};
  const c=new Proxy(methods,{get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden live read '+String(k));return t[k];},
    set(){assert.fail('forbidden live assignment');}});
  maker.finish(c,o,s=>{stage=s;});return actions;
}
function compareUnobserved(r) {
  maker.check(r);const expected=JSON.parse(JSON.stringify(r.calc));
  const c=capture.prepare(r.options);fullMsPages(c);registers(c);program(c);aligned(c);
  maker.finish(c,r.options);c.runFrames(3);aligned(c);fullMsPages(c);registers(c);program(c);
  assert.deepEqual(JSON.parse(JSON.stringify(c)),expected);
  return createHash('sha256').update(JSON.stringify(c)).digest('hex');
}
const actions=record();
assert.deepEqual(actions,record({incoming:'must not read',p3:'must not read',values:['must not read'],fullUpper:['must not read']}));
assert.deepEqual(actions.filter(a=>a[0]==='key'&&a[2].startsWith('logical-carrier-')).map(a=>a[1]),maker.makerKeys);
const keys=actions.filter(a=>a[0]==='key').length;
const frames=keys*2+actions.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0);
console.log('PASS fixed keyboard maker:',JSON.stringify({keys,frames,noHiddenReads:true}));
if(process.env.K1_LOGICAL_UNOBSERVED) {
  const r=maker.run();console.log('PASS complete observed/unobserved state:',compareUnobserved(r));
  r.traced.events.length=r.traced.writes.length=0;
}
module.exports={record,compareUnobserved};
