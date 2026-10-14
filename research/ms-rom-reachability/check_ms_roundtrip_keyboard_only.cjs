#!/usr/bin/env node
'use strict';
// Static API-contract check, NOT an emulator correctness test. Recording the
// live finish() on a key-only sink rejects hidden chip/register/program reads
// or writes. Real correctness is checked separately on the unchanged emulator.
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {finish}=require('./probe_ms_read6_roundtrip.cjs');
function record(display) {
  const actions=[],counts={};let stage='';
  const allowed={
    press(key){assert.equal(typeof key,'string');actions.push(['key',key]);counts[stage]=(counts[stage]??0)+1;return this;},
    pressSequence:MK61.prototype.pressSequence,
    inputNumber:MK61.prototype.inputNumber,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n]);return this;},
    displayText(){return display;},
  };
  const calc=new Proxy(allowed,{
    get(target,key){assert.ok(Object.hasOwn(target,key),'live protocol requested forbidden calculator access: '+String(key));return target[key];},
    set(){assert.fail('live protocol assigned calculator state');},
  });
  finish(calc,{},label=>{stage=label;});
  return {actions,counts};
}
const a=record('0,'),b=record('THIS DISPLAY MUST NOT CONTROL EXECUTION');
assert.deepEqual(a.actions,b.actions,'all keys and waits are independent of diagnostic display text');
const keys=a.actions.filter(a=>a[0]==='key').length,wait=a.actions.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0);
const stages={};for(const [name,n] of Object.entries(a.counts)){const head=name.startsWith('relocate-')?'relocate-copies':name.split('/')[0];stages[head]=(stages[head]??0)+n;}
console.log('PASS: live finish() uses only native keys, fixed waits and ignored passive display text. No state/register/program getter or setter, alignment helper, import, reset or display-dependent branch is accessible.');
console.log(JSON.stringify({keys,extraWaitFrames:wait,totalFrames:2*keys+wait,stages}));
console.log('LIMIT: this checks the keyboard API contract, not the numerical or timing correctness of these actions.');
