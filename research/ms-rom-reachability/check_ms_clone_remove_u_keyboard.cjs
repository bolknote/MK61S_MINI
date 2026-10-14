#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {finish,displayGuard}=require('./probe_ms_clone_remove_u.cjs');
function record(responses,o={}) {
  let stage='';const actions=[],reads=[];
  const methods={
    press(k){assert.equal(typeof k,'string');actions.push(['key',k]);return this;},
    pressSequence:MK61.prototype.pressSequence,inputNumber:MK61.prototype.inputNumber,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n]);return this;},
    displayText(){assert.ok(stage.startsWith('clone-swap-'));const value=responses[reads.length];reads.push(value);return value;},
  };
  const c=new Proxy(methods,{
    get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden live access '+String(k));return t[k];},
    set(){assert.fail('forbidden live assignment');},
  });
  const result=finish(c,o,label=>{stage=label;});return {result,actions,reads};
}
for(const displays of [[displayGuard],[',',displayGuard],[',',',',displayGuard]]) {
  const a=record(displays);assert.deepEqual(a.result.displays,displays);assert.deepEqual(a.reads,displays);
  assert.deepEqual(a.actions,record(displays,{fullUpper:['not read'],values:['not read'],tailValue:'not used'}).actions);
  const keys=a.actions.filter(x=>x[0]==='key').length,waits=a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  console.log('PASS public-display-only clone/erase:',JSON.stringify({displays,keys,extraFrames:waits,totalFrames:keys*2+waits}));
}
assert.throws(()=>record(['0,']),/Unexpected visible display/);
assert.throws(()=>record([',',',',',']),/No guard display/);
console.log('PASS fail-closed stop; no hidden state, getters, setters, resets or alignment. Native fixture is separate.');
module.exports={record};
