#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {peek}=require('./k1-frame-boundary-probe.cjs');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const actions=[['1'],[','],['2'],['В↑'],['3'],['+'],['X→П','0'],
  ['Сx'],['K','Сx'],['K','8'],['F',','],['П→X','0']];
function perform(c,record=()=>{}) {
  actions.forEach((keys,i)=>{
    record();c.pressSequence(keys).runFrames(i%3);
  });
  record();c.runFrames(1);
}
const c=aligned(new MK61()),expected=[];
let frame=0;
const positions=new Set([0]);
for(const [i,keys] of actions.entries()) {
  frame+=2*keys.length+i%3;positions.add(frame*560);
}
const observed=trace(c,c=>perform(c,()=>expected.push(peek(c))),
  {extraIps:Array.from({length:256},(_,i)=>i),
    ringAt:e=>positions.has(e.command)});
assert.deepEqual(observed.events.filter(e=>e.ring).map(e=>e.ring),expected);
const d=aligned(new MK61());perform(d);
assert.deepEqual(JSON.parse(JSON.stringify(c)),JSON.parse(JSON.stringify(d)));
console.log('PASS frame-only reader: all 630 tetras at',expected.length,
  'boundaries, all three phases; arithmetic, store/recall and logical markers.');
console.log('PASS all native calculator fields equal a fresh run without observers.');
console.log('LIMIT: boundary snapshots do not audit transient writes or prove a protocol.');
