#!/usr/bin/env node
'use strict';
// A separate surface-only contract: no fixture, state, or numeric getter is
// exposed to the live quiet-request continuation.
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {finish}=require('./probe_ms_clone_quiet_request.cjs');
const guard='-1,2345678-42';
const ack=[['F',','],['↔'],['↔']];
function record(responses,o={},operation=finish) {
  let stage='';const actions=[],reads=[];
  const methods={
    press(k){assert.equal(typeof k,'string');actions.push(['key',k,stage]);return this;},
    pressSequence:MK61.prototype.pressSequence,inputNumber:MK61.prototype.inputNumber,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n,stage]);return this;},
    displayText(){assert.ok(stage.startsWith('clone-swap-'));const v=responses[reads.length];reads.push(v);return v;},
  };
  const c=new Proxy(methods,{
    get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden live access '+String(k));return t[k];},
    set(){assert.fail('forbidden live assignment');},
  });
  const result=operation(c,o,label=>{stage=label;});return {actions,reads,result};
}
if(require.main===module) {
  for(const responses of [[guard],[',',guard],[',',',',guard]])for(const afterQuiet of [undefined,ack]) {
    const o={afterQuiet},r=record(responses,o);assert.deepEqual(r.reads,responses);
    assert.deepEqual(r.actions,record(responses,{...o,sourceValue:'not read',fullUpper:['not read'],independentP8:'not read'}).actions);
    for(let i=0;i<3;i++) {
      const stage='clone-quiet-'+i;
      assert.deepEqual(r.actions.filter(x=>x[2]===stage),[
        ...(i?[['wait',1,stage]]:[]),['key','K',stage],['key','×',stage],['wait',8,stage]]);
    }
    for(const [i,keys] of (afterQuiet??[['F',',']]).entries()) {
      const stage='clone-quiet-after-'+i;
      assert.deepEqual(r.actions.filter(x=>x[2]===stage),[...keys.map(k=>['key',k,stage]),['wait',8,stage]]);
    }
    const keys=r.actions.filter(x=>x[0]==='key').length;
    const frames=2*keys+r.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
    console.log('PASS quiet request uses only keys and declared public display:',JSON.stringify({ack:!!afterQuiet,keys,frames}));
  }
  assert.throws(()=>record(['0,']),/Unexpected visible display/);
  assert.throws(()=>record([',',',',',']),/No guard display/);
  console.log('LIMIT: fixture, canonical input class, numeric preservation and timing are separate obligations.');
}
module.exports={record};
