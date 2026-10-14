#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const p=require('./k1-bank-v-capture.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function record(o={}) {
  let stage='';const actions=[];
  const methods={press(k){actions.push(['key',k,stage]);return this;},pressSequence:MK61.prototype.pressSequence,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n,stage]);return this;}};
  const c=new Proxy(methods,{get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden live read '+String(k));return t[k];},
    set(){assert.fail('forbidden live assignment');}});
  p.finish(c,o,s=>{stage=s;});return actions;
}
const expected=record();
assert.deepEqual(expected,record({incoming:'not read',p3:'not read',values:['not read'],fullUpper:['not read']}));
assert.deepEqual(expected.filter(a=>a[0]==='key').map(a=>a[1]),
  ['Сx','В↑','В↑','В↑','+','Сx','K','-','ВП','K','0','П→X','0','П→X','0','X→П','0']);
assert.equal(expected.filter(a=>a[0]==='key').length,17);
assert.equal(34+expected.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0),138);
console.log('PASS capture keyboard surface: 17 keys / 138 frames; no display, register, program, internal-state or fixture access.');
if(process.env.K1_BANK_UNOBSERVED) {
  const r=p.run();require('./k1-bank-v-capture-check.cjs').check(r);
  const expectedState=JSON.parse(JSON.stringify(r.calc));r.traced.events.length=r.traced.writes.length=0;
  const c=p.prepare();fullMsPages(c);registers(c);program(c);aligned(c);
  p.finish(c);c.runFrames(3);aligned(c);fullMsPages(c);registers(c);program(c);
  assert.deepEqual(JSON.parse(JSON.stringify(c)),expectedState);
  console.log('PASS complete observed/unobserved state:',createHash('sha256').update(JSON.stringify(c)).digest('hex'));
}
module.exports={record};
