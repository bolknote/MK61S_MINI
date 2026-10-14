#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {finish}=require('./probe_ms_marker_clone_visible_stop.cjs');
function record(responses,o={}) {
  let stage='';const actions=[],reads=[];
  const methods={
    press(k){actions.push(['key',k]);return this;},pressSequence:MK61.prototype.pressSequence,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n]);return this;},
    displayText(){
      if(!stage.startsWith('clone-swap'))return 'ignored prefix display';
      const value=responses[reads.length];reads.push(value);return value;
    },
  };
  const c=new Proxy(methods,{
    get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden live access '+String(k));return t[k];},
    set(){assert.fail('forbidden live state assignment');},
  });
  const result=finish(c,o,label=>{stage=label;});return {result,actions,reads};
}
for(const displays of [['0,'],[',','0,'],[',',',','0,']]) {
  const a=record(displays);assert.deepEqual(a.result.displays,displays);assert.deepEqual(a.reads,displays);
  assert.deepEqual(a.actions,record(displays,{fullUpper:['untrusted'],values:['not read']}).actions);
  const keys=a.actions.filter(x=>x[0]==='key').length;
  const waits=a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  console.log('PASS visible-only stop:',JSON.stringify({displays,keys,extraFrames:waits,totalFrames:keys*2+waits}));
}
assert.throws(()=>record(['unexpected']),/Unexpected visible display/);
assert.throws(()=>record([',',',',',']),/No visible zero/);
console.log('PASS fail-closed display controls; no hidden state, getters, setters, reset or alignment. This is an adaptive, NOT read-free, keyboard protocol.');
module.exports={record};
