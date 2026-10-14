#!/usr/bin/env node
'use strict';
// Read-free fixed keyboard program; preparation and observations are outside it.
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {finish}=require('./probe_ms_lower_exchange.cjs');
function record(display,options={},operation=finish) {
  const actions=[],counts={};let stage='';
  const allowed={
    press(key){assert.equal(typeof key,'string');actions.push(['key',key]);counts[stage]=(counts[stage]??0)+1;return this;},
    pressSequence:MK61.prototype.pressSequence,inputNumber:MK61.prototype.inputNumber,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n]);return this;},
    displayText(){return display;},
  };
  const calc=new Proxy(allowed,{
    get(target,key){assert.ok(Object.hasOwn(target,key),'forbidden live access: '+String(key));return target[key];},
    set(){assert.fail('live calculator state assigned');},
  });
  operation(calc,options,label=>{stage=label;});return {actions,counts};
}
function main() {
  const baseline=record('0,');
  for(const o of [{},{phaseOffset:1},{phaseOffset:2},{settleFrames:12,markerFrames:8}]) {
    const a=record('0,',o),b=record('THIS IS NOT A NUMBER',o);
    assert.deepEqual(a.actions,b.actions);
    assert.deepEqual(a.actions.filter(x=>x[0]==='key'),baseline.actions.filter(x=>x[0]==='key'));
    const keys=a.actions.filter(x=>x[0]==='key').length,wait=a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
    console.log('PASS fixed keyboard-only lower exchange:',JSON.stringify({options:o,keys,extraWaitFrames:wait,totalFrames:2*keys+wait}));
  }
  assert.deepEqual(record('0,',{bank:['9E99'],values:['-1E-99'],fullUpper:['123']}).actions,baseline.actions);
  console.log('PASS: no state/register/program reads, setters, imports, reset, alignment, or display-dependent choice.');
  console.log('LIMIT: API/sequence check only, not a universal native-ROM or physical-timing theorem.');
}
if(require.main===module)main();
module.exports={record};
