#!/usr/bin/env node
'use strict';
// Counterexamples keep the omitted operation's total frame duration.
const assert=require('node:assert/strict');
const probe=require('./k1-ytv-rcl-closed.cjs');
const lastx=require('./k1-z-backed-lastx.cjs');
function omit(index,expected) {
  const actions=probe.defaults.deepTail.map((x,i)=>i===index?[]:x);
  const waits=Array(7).fill(8);waits[index]=8+2*probe.defaults.deepTail[index].length;
  const r=probe.run({deepTail:actions,deepTailWaits:waits,stopAfterClear:true});
  const lost=r.before[expected].slice(2),failures=r.rows.filter(e=>e.missing.length);
  assert.ok(failures.length);assert.deepEqual(failures.at(-1).missing,[lost]);
  assert.ok(failures.every(e=>e.missing.length===1&&e.missing[0]===lost));
  assert.equal(failures[0].stage,index===5?'immediate':'deep/tail-phase-6');
  return {omitted:index===5?'equal-operand subtraction':'restoring NOP',sameFrameDuration:true,
    firstLoss:failures[0].stage,lost,wholeMachineImpossibility:false};
}
function literal() {
  const r=lastx.run({deepTail:[['K','0'],['F','В↑'],['Сx'],['1']],deepTailPhases:[1,1,0,0]});
  const lost=r.before.V.slice(2);
  assert.deepEqual(r.rows.filter(e=>e.missing.length).map(e=>[e.stage,e.missing]),
    [['immediate',[lost]],['done',[lost]]]);
  return {rejected:'Cx then digit 1 after LastX',lost,frameEvidenceOnly:true};
}
if(require.main===module) {
  const which=process.env.K1_YTV_NEGATIVE_CASE;
  if(!which||which==='drop')console.log('PASS missing reserve:',JSON.stringify(omit(5,'V')));
  if(!which||which==='nop')console.log('PASS missing NOP:',JSON.stringify(omit(3,'U')));
  if(!which||which==='literal')console.log('PASS rejected literal:',JSON.stringify(literal()));
}
module.exports={omit,literal};
