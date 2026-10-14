#!/usr/bin/env node
'use strict';
// API-only check: correctness and ROM paths are checked separately.
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {finish}=require('./probe_ms_upper_read4.cjs');
function record(display,options={}) {
  const actions=[],counts={};let stage='';
  const allowed={
    press(key){assert.equal(typeof key,'string');actions.push(['key',key]);counts[stage]=(counts[stage]??0)+1;return this;},
    pressSequence:MK61.prototype.pressSequence,
    inputNumber:MK61.prototype.inputNumber,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n]);return this;},
    displayText(){return display;},
  };
  const calc=new Proxy(allowed,{
    get(target,key){assert.ok(Object.hasOwn(target,key),'forbidden live calculator access: '+String(key));return target[key];},
    set(){assert.fail('live protocol assigned calculator state');},
  });
  finish(calc,options,label=>{stage=label;});return {actions,counts};
}
for(const options of [{},{clearInitialU:true}]) {
  const a=record('0,',options),b=record('IGNORED DISPLAY',options);assert.deepEqual(a.actions,b.actions);
  const keys=a.actions.filter(a=>a[0]==='key').length;
  const wait=a.actions.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0);
  console.log('PASS: four-word reader uses fixed keys and waits; no live state/register/program reads, setters, imports, reset or display-dependent branch.');
  console.log(JSON.stringify({options,keys,extraWaitFrames:wait,totalFrames:2*keys+wait}));
}
console.log('LIMIT: static keyboard API check, not a proof of emulator or timing correctness.');
