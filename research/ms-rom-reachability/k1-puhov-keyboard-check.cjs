#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const historical=require('./k1-puhov-ring-probe.cjs');
const retained=require('./k1-q-retained-probe.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function record(o,operation) {
  const actions=[];let stage='';
  const methods={press(k){actions.push(['key',k,stage]);return this;},pressSequence:MK61.prototype.pressSequence,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n,stage]);return this;}};
  const c=new Proxy(methods,{get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden live read '+String(k));return t[k];},
    set(){assert.fail('forbidden live assignment');}});
  operation(c,o,s=>{stage=s;});return actions;
}
function stack(c) {
  assert.equal(c.ir2a.tickIndex,84);
  const addresses={X1:[5,34],X:[4,34],Y:[3,34],Z:[2,118],T:[2,160]};
  return Object.fromEntries(Object.entries(addresses).map(([n,[chip,end]])=>[n,
    Array.from({length:12},(_,i)=>c.memoryForChip(chip)[end-3*i].toString(16).toUpperCase()).join('')]));
}
function sample(o={}) {
  o={...historical.defaults,...o,saveQ:true};
  const c=capture.prepare(o),before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  aligned(c);retained.finish(c,o);c.runFrames(3);aligned(c);
  const after=fullMsPages(c),afterRegisters=registers(c),afterProgram=program(c),visible=stack(c);
  return {c,options:o,before,beforeRegisters,beforeProgram,after,afterRegisters,afterProgram,visible};
}
function compact(o={}) {
  const {c,options,before,beforeRegisters,beforeProgram,after,afterRegisters,afterProgram,visible}=sample(o);
  const [u,v,w,q]=['U','V','W','Q'].map(n=>before[n].slice(2)),p=beforeRegisters[0],m='9990FFFFFFF0';
  assert.deepEqual(afterRegisters,beforeRegisters.map((x,i)=>i===0?q:x));
  assert.deepEqual(afterProgram,beforeProgram);
  assert.deepEqual(after,{...before,U:before.U.slice(0,2)+m,V:before.V.slice(0,2)+u,W:before.W.slice(0,2)+v});
  assert.deepEqual(['X','Y','Z','T'].map(n=>visible[n]),[q,options.neutralMarker?'0000FFFFFFF0':m,w,p]);
  return {options,q,all23StillLive:true,cleanupPending:true,sha256:createHash('sha256').update(JSON.stringify(c)).digest('hex')};
}
function negativePhase() {
  const r=sample({phaseOffset:2}),m='9990FFFFFFF0';
  const [u,v,w,q,a]=['U','V','W','Q','P7'].map(n=>r.before[n].slice(2));
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((x,i)=>i===7?m:x));
  assert.deepEqual(r.after,{...r.before,U:r.before.U.slice(0,2)+m,V:r.before.V.slice(0,2)+u,
    W:r.before.W.slice(0,2)+m,Q:r.before.Q.slice(0,2)+v,
    P7:r.before.P7.slice(0,2)+q,P8:r.before.P8.slice(0,2)+a});
  assert.deepEqual(['X','Y','Z','T'].map(n=>r.visible[n]),[m,w,r.beforeRegisters[0],m]);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  return {phase:2,validCapture:false,lostStoredValues:['old P7','old sixth Ms word'],programHeld:true};
}
function markerTimingControl() {
  const r=sample({phaseOffset:0,neutralMarker:true}),m='9990FFFFFFF0',n='0000FFFFFFF0';
  const [u,v,q,a]=['U','V','Q','P7'].map(k=>r.before[k].slice(2));
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((x,i)=>i===7?n:x));
  assert.deepEqual(r.after,{...r.before,U:r.before.U.slice(0,2)+m,V:r.before.V.slice(0,2)+u,
    W:r.before.W.slice(0,2)+n,Q:r.before.Q.slice(0,2)+v,
    P7:r.before.P7.slice(0,2)+q,P8:r.before.P8.slice(0,2)+a});
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  const waitOnly=compact({phaseOffset:2,markerDelayFrames:20});
  return {neutralMarkerPhase0Fails:true,unchangedMarkerWithEqualWaitPasses:waitOnly.all23StillLive,
    phaseProblemSolved:false};
}
function compareUnobserved(expected,o,operation=retained.finish) {
  const c=capture.prepare(o);fullMsPages(c);registers(c);program(c);aligned(c);
  operation(c,o);c.runFrames(3);aligned(c);fullMsPages(c);registers(c);program(c);
  assert.deepEqual(JSON.parse(JSON.stringify(c)),expected);
  return createHash('sha256').update(JSON.stringify(c)).digest('hex');
}
if(require.main===module) {
  for(const [name,o,operation] of [['read',{},historical.finish],['fifo',{rotate:true},historical.finish],
    ['retained-q',{saveQ:true},retained.finish]]) {
    const actions=record(o,operation);
    assert.deepEqual(actions,record({...o,incoming:'not read',values:['not read'],fullUpper:['not read'],p3:'not read'},operation));
    const keys=actions.filter(a=>a[0]==='key').length;
    const frames=keys*2+actions.filter(a=>a[0]==='wait').reduce((n,a)=>n+a[1],0);
    console.log('PASS keyboard surface:',JSON.stringify({name,keys,frames,noHiddenReads:true}));
  }
  if(process.env.K1_PUHOV_COMPACT) {
    const cases=[{phaseOffset:0},{phaseOffset:1},
      {phaseOffset:0,incoming:'301',values:['-1.2345678E-42','622','733','844']},
      {phaseOffset:0,values:['12345678','822','833','844']}];
    const chosen=process.env.K1_PUHOV_COMPACT_CASE===undefined?cases:[cases[Number(process.env.K1_PUHOV_COMPACT_CASE)]];
    assert.ok(chosen.every(Boolean));
    for(const o of chosen)console.log('PASS observer-free retained Q:',JSON.stringify(compact(o)));
  }
  if(process.env.K1_PUHOV_PHASE_NEGATIVE)console.log('PASS rejected third phase:',JSON.stringify(negativePhase()));
  if(process.env.K1_PUHOV_MARKER_TIMING)console.log('PASS marker/timing control:',JSON.stringify(markerTimingControl()));
}
module.exports={record,stack,sample,compact,negativePhase,markerTimingControl,compareUnobserved};
