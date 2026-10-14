#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {finish}=require('./probe_ms_clone_load_x.cjs');
const displayGuard='-1,2345678-42';
function record(responses,o={}) {
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
  const result=finish(c,o,label=>{stage=label;});return {actions,reads,result};
}
for(const responses of [[displayGuard],[',',displayGuard],[',',',',displayGuard]]) {
  const r=record(responses);assert.deepEqual(r.reads,responses);
  assert.deepEqual(r.actions,record(responses,{sourceValue:'not read',fullUpper:['not read'],independentP8:'not read'}).actions);
  assert.deepEqual(r.actions.filter(x=>x[2]==='clone-load-x'),
    [['key','П→X','clone-load-x'],['key','8','clone-load-x'],['wait',8,'clone-load-x']]);
  const keys=r.actions.filter(x=>x[0]==='key').length;
  const frames=2*keys+r.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
  console.log('PASS conditional numeric loader, only keys and public stop display:',JSON.stringify({keys,frames}));
  const read=record(responses,{tailActions:[['F',',']]});
  assert.deepEqual(read.reads,responses);
  assert.deepEqual(read.actions.filter(x=>x[2]==='clone-load-tail-0'),
    [['key','F','clone-load-tail-0'],['key',',','clone-load-tail-0'],['wait',8,'clone-load-tail-0']]);
  assert.deepEqual(read.actions,record(responses,{tailActions:[['F',',']],
    sourceValue:'not read',fullUpper:['not read'],independentP8:'not read'}).actions);
  assert.equal(read.actions.filter(x=>x[0]==='key').length,keys+2);
  assert.equal(2*(keys+2)+read.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),frames+12);
  console.log('PASS sixth-word continuation has no hidden reads:',JSON.stringify({keys:keys+2,frames:frames+12}));
}
assert.throws(()=>record(['0,']),/Unexpected visible display/);
assert.throws(()=>record([',',',',',']),/No guard display/);
console.log('LIMIT: numeric source class and fixture preconditions are checked separately, not discovered by hidden live reads.');
module.exports={record};
