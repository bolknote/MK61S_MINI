#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const proxy=require('./check_ms_lower_exchange_keyboard.cjs');
const p=require('./probe_ms_lower_guarded_exchange.cjs');
const guard=require('./probe_ms_u_guard.cjs');
const record=(display,o={})=>proxy.record(display,o,p.finish);
const frames=r=>r.actions.reduce((n,a)=>n+(a[0]==='key'?2:a[1]),0);
function main() {
  const baseline=record('0,');
  for(const o of [{},{phaseOffset:1},{phaseOffset:2},{settleFrames:12,markerFrames:8}]) {
    const a=record('0,',o),b=record('not a number',o);
    assert.deepEqual(a.actions,b.actions);
    assert.deepEqual(a.actions.filter(x=>x[0]==='key'),baseline.actions.filter(x=>x[0]==='key'));
    const keys=a.actions.filter(x=>x[0]==='key').length;assert.equal(keys,446);
    console.log('PASS fixed guarded exchange keyboard:',JSON.stringify({options:o,keys,extraWaitFrames:frames(a)-2*keys,totalFrames:frames(a)}));
  }
  assert.deepEqual(record('anything',{bank:['-1E-99'],values:['123'],fullUpper:['0']}).actions,baseline.actions);
  for(const wait of [8,9,10,11,12]) {
    const runs=[1,2,3].map(rounds=>proxy.record('ignored',{settleFrames:wait,rounds},guard.finish));
    const step=frames(runs[1])-frames(runs[0]);assert.equal(frames(runs[2])-frames(runs[1]),step);
    assert.equal(step,54+10*wait+(wait%3===0?1:0));
    assert.equal(new Set([0,1,2].map(i=>(i*step)%3)).size,3);
    console.log('PASS phase schedule, not native convergence:',JSON.stringify({wait,roundStepFrames:step,residues:[0,step%3,(2*step)%3]}));
  }
  const old=[1,2,3].map(rounds=>proxy.record('ignored',{settleFrames:12,rounds,phaseSweep:false},guard.finish));
  assert.equal((frames(old[1])-frames(old[0]))%3,0);
  console.log('PASS negative arithmetic control: without the extra wait, 12-frame rounds repeat the SAME phase.');
  console.log('LIMIT: no state-based branch, setters, imports, resets or live alignment; phase coverage alone does not prove all ROM input states or physical timing.');
}
if(require.main===module)main();
module.exports={record};
