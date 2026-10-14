#!/usr/bin/env node
'use strict';
// Exactly two permutation candidates before the preserving NOP exit.
// Each run is a fresh keyboard execution. No imported state or hidden reads.
const assert=require('node:assert/strict');
const restored=require('./k1-vw-nop-restored.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const operations={swap:['↔'],rotate:['F',',']};
const defaults={...restored.defaults,fullUpper:['-1E-99','-2E-50','9033','9044'],
  upperOperation:'swap',upperLeadPhase:0};
function finish(c,o={},record=()=>{}) {
  const name=o.upperOperation??'swap',lead=o.upperLeadPhase??0;
  assert.ok(Object.hasOwn(operations,name));
  assert.ok(Number.isInteger(lead)&&lead>=0&&lead<3);
  const keys=operations[name],duration=keys.length*2+8;
  // Restore the original modulo-three position of the following NOP using
  // only this fixed public schedule, not an observed internal phase.
  const pad=(3-(lead+duration)%3)%3;
  restored.finish(c,o,stage=>{
    if(stage==='nop/phase') {
      record('insert/phase');c.runFrames(lead);
      stack.act(c,record,'insert/op',keys);
      record('insert/after');c.runFrames(pad);
    }
    record(stage);
  });
}
function run(o={}) {return frame.run(module.exports,o);}
function traced(o={}) {
  o={...defaults,...o};
  return cap.run(o,finish,['insert/op','nop/read','nop/tail-0','nop/tail-1',
    'restore/first/push','restore/second/push']);
}
function summary(r) {
  const stages=['insert/phase','insert/after','nop/read','nop/tail-0',
    'nop/tail-1','restore/phase','restore/first/push-marker-0',
    'restore/rotate-0','restore/second/push-marker-0','post/manual','done'];
  return {options:r.options,rows:frame.brief(r).rows.filter(x=>stages.includes(x.stage))};
}
function checkNegative(r) {
  const at=name=>r.rows.find(x=>x.stage===name);
  const before=at('insert/phase'),after=at('insert/after'),nop=at('nop/read');
  const op=r.options.upperOperation,phase=r.options.upperLeadPhase;
  const [u,v,q,p]=['Y','U','Z','Q'].map(n=>before.values[n]);
  const expected=op==='swap'?(phase===1?[p]:[v]):(phase===0?[u,v,q]:[p]);
  assert.deepEqual(before.missing,[]);
  assert.deepEqual(after.missing,expected);
  assert.deepEqual(nop.values,after.values,'phase padding does not hide recovery');
  assert.equal(nop.phase,168,'all cases keep the established NOP phase');
  for(const n of ['P7','P8','P9','P10'])
    assert.equal(after.values[n],before.values[n],n+' has not yet been permuted');
  assert.ok(expected.every(word=>r.rows.at(-1).missing.includes(word)),
    'the unchanged NOP cleanup does not return the lost originals');
  return {operation:op,phase,firstMissing:expected,upperWordsUnchangedAfterInsertion:true,
    testedContinuationRepairsLoss:false,fullK1:false,generalImpossibility:false};
}
module.exports={defaults,operations,finish,run,traced,summary,checkNegative};
if(require.main===module) {
  const r=run(JSON.parse(process.argv[2]??'{}'));
  console.log(JSON.stringify({check:checkNegative(r),...summary(r)},null,2));
}
