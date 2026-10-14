#!/usr/bin/env node
'use strict';
// Compare two complete fresh keyboard runs. Neither state is imported into
// the other calculator. Equal endpoints would disprove post-hoc recovery
// for this particular continuation, not every unchanged-ROM K1 protocol.
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const probe=require('./k1-zq-origin-entry.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
function snapshot(c) {
  // JSON equality must not silently omit a buffer, NaN, a Map, accessor or
  // non-enumerable mutable field. Native state consists of finite scalar
  // values, arrays and the chip/calculator class instances. The fixture
  // installs four stateless guards against state setters; any restored own
  // native method must be identical to its prototype method.
  const seen=new Set();
  const guards=new Set(['loadProgram','writeCommand','setRegister','writeNumber']);
  function inspect(v) {
    if(v===null||typeof v==='string'||typeof v==='boolean')return;
    if(typeof v==='number'){assert.ok(Number.isFinite(v));return;}
    assert.equal(typeof v,'object','only serializable native state');
    assert.equal(Object.prototype.toString.call(v),Array.isArray(v)?'[object Array]':'[object Object]');
    if(seen.has(v))return;seen.add(v);
    for(const k of Reflect.ownKeys(v)) {
      if(Array.isArray(v)&&k==='length')continue;
      assert.equal(typeof k,'string');
      const d=Object.getOwnPropertyDescriptor(v,k);
      assert.ok(d.enumerable&&!d.get&&!d.set,'every native field is serialized: '+k);
      if(typeof d.value==='function') {
        if(v===c&&guards.has(k)) {
          assert.equal(d.value.toString(),"()=>{throw new Error('Forbidden state setter: '+name);}");
          assert.throws(()=>d.value(),{message:'Forbidden state setter: '+k});
        } else assert.equal(d.value,Object.getPrototypeOf(v)[k],'only unchanged native methods may be omitted');
      } else inspect(d.value);
    }
  }
  inspect(c);return JSON.parse(JSON.stringify(c));
}
const hash=c=>createHash('sha256').update(JSON.stringify(c)).digest('hex');

function differences(a,b,path='') {
  if(a===b)return [];
  if(a&&b&&typeof a==='object'&&typeof b==='object') {
    assert.deepEqual(Object.keys(a),Object.keys(b));
    return Object.keys(a).flatMap(k=>differences(a[k],b[k],path?path+'.'+k:k));
  }
  return [[path,a,b]];
}

function run(q) {
  const o={...probe.defaults,values:probe.defaults.values.slice()};o.values[0]=q;
  const c=cap.prepare(o),initial=fullMsPages(c);registers(c);program(c);aligned(c);
  probe.finish(c,o);
  const before=snapshot(c),beforeRing=peek(c);
  assert.equal(raw(beforeRing.P7),initial.Q.slice(2));
  stack.act(c,()=>{},'swap',['↔']);
  const immediate=snapshot(c),immediateRing=peek(c);
  c.runFrames(3);
  return {q,initial,before,beforeRing,immediate,immediateRing,after:snapshot(c),afterRing:peek(c)};
}

function check(a,b) {
  assert.notEqual(a.initial.Q,b.initial.Q);
  const before=differences(a.before,b.before),immediate=differences(a.immediate,b.immediate),after=differences(a.after,b.after);
  assert.deepEqual(differences(a.initial,b.initial),[['Q',a.initial.Q,b.initial.Q]]);
  assert.deepEqual(before,[['ir2b.memory.238',8,7]],'only one native memory tetra differs before the final key');
  assert.deepEqual(differences(a.beforeRing,b.beforeRing),[['P7.28',8,7]]);
  assert.deepEqual(immediate,[],'complete states coincide immediately after the ordinary swap key');
  assert.deepEqual(after,[],'complete states also coincide after three ordinary frames');
  assert.equal(raw(a.afterRing.P7),'143912345678');
  assert.equal(raw(b.afterRing.P7),'143912345678');
  assert.equal(hash(a.after),'e487a1946ffe4e722ac6f7423149b8664252aafed9934f3f9dba35e0aa80ed2c');
  return {inputs:[a.q,b.q],beforeDifferences:before,immediateDifferences:immediate,
    afterDifferences:after,identicalCompleteFinalState:after.length===0,
    hashes:[hash(a.after),hash(b.after)],fullK1Impossibility:false};
}

if(require.main===module) {
  const a=run('-1.2345678E-42');console.log('FIRST complete',hash(a.after));
  const b=run('-1.2345678E-43');console.log('PASS exact full-machine collision:',JSON.stringify(check(a,b),null,2));
}
module.exports={run,check,differences,hash,snapshot};
