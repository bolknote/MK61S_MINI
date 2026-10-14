#!/usr/bin/env node
'use strict';
// Dynamic API firewall around the live protocol, not fixture or assertions.
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {finish}=require('./probe_ms_read8_roundtrip.cjs');
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
function main() {
  for(const readOnly of [false,true]) {
    const baseline=record('0,',{readOnly});
    for(const options of [{},{phaseOffset:1},{phaseOffset:2},{settleFrames:12,markerFrames:8}]) {
      const o={...options,readOnly},a=record('0,',o),b=record('IGNORED DISPLAY',o);
      assert.deepEqual(a.actions,b.actions);
      assert.deepEqual(a.actions.filter(x=>x[0]==='key'),baseline.actions.filter(x=>x[0]==='key'));
      const keys=a.actions.filter(x=>x[0]==='key').length;
      const wait=a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
      console.log('PASS fixed keyboard-only read8:',JSON.stringify({options:o,keys,extraWaitFrames:wait,totalFrames:2*keys+wait}));
    }
    assert.deepEqual(record('0,',{readOnly,initialE:'123',values:['-1E-99'],fullUpper:['9E99']}).actions,baseline.actions,
      'fixture values cannot influence the live key sequence');
  }
  console.log('PASS: no live state/register/program reads, setters, imports, reset, alignment or display-dependent branch.');
  console.log('LIMIT: fixed-key/API check, not native ROM correctness or physical timing.');
}
if(require.main===module)main();
module.exports={record};
