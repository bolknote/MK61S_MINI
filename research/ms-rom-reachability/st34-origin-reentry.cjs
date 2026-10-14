#!/usr/bin/env node
'use strict';
// Source-driven fixed keyboard extensions of the relocated selector reader.
const assert=require('node:assert/strict');
const {run,prepareSelector,finishSelector}=require('./st34-origin-trace.cjs');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {install,fixtures}=require('./check_partial_k2_program_scan.cjs');
const positions=[0,3,9,12,18,21];
const lane=(a,n)=>a.filter((_,i)=>i%3===n).slice(0,12);
const compact=e=>({ip:e.ip.toString(16).toUpperCase(),command:e.command,
  rTail:e.r.slice(30,36),stTail:e.st.slice(30,36),r23:e.r[23],
  A:lane(e.r,0),B:lane(e.r,1),C:lane(e.r,2),key:[e.keyX,e.keyY]});

function extension(keys,{selector=4,phaseOffset=0,settleFrames=4}={}) {
  const initial=run({selector,phaseOffset,settleFrames}),calc=initial.calc;
  const before={r:calc.ik1302.r.slice(),st:calc.ik1302.stack.slice()};
  const result=trace(calc,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true});
  const events=result.events,active=events.filter((e,i)=>i===0||e.ip!==events[i-1].ip);
  const points=events.filter((e,i)=>i===0||e.st.slice(30,36).join()!=events[i-1].st.slice(30,36).join()||
    [0x8C,0x91,0x92,0x93,0x94,0x95,0x98,0x9A,0x8D,0xDC,0xDE,0xD4].includes(e.ip));
  return {calc,before,result,report:{keys,selector,route:active.map(e=>e.ip.toString(16).toUpperCase()),
    points:points.map(compact),after:{rTail:calc.ik1302.r.slice(30,36),
      stTail:calc.ik1302.stack.slice(30,36),A:lane(calc.ik1302.r,0),B:lane(calc.ik1302.r,1),C:lane(calc.ik1302.r,2)}}};
}
function check(keys,{safe=false,mirror=false}={}) {
  const r=extension(keys),events=r.result.events,payload=positions.map(n=>r.before.r[n]);
  const firstEE=events.findIndex(e=>e.ip===0xEE),first8C=events.findIndex(e=>e.ip===0x8C);
  const first8D=events.findIndex(e=>e.ip===0x8D);
  const afterPayload=positions.map(n=>r.calc.ik1302.r[n]);
  if(first8C>=0&&(firstEE<0||first8C<firstEE)) {
    assert.ok(first8D>first8C);
    assert.deepEqual(positions.map(n=>events[first8D].r[n]),payload,'first restore returns all six cache tetras');
    assert.deepEqual(events[first8D].r.slice(33,36),[4,15,5]);
    assert.deepEqual(events[first8D].st.slice(33,36),[9,15,5]);
  }
  if(safe) {
    assert.equal(firstEE,-1);assert.equal(first8C,-1);
    assert.deepEqual(afterPayload,payload);
    assert.deepEqual(r.calc.ik1302.stack.slice(33,36),[4,15,5]);
    assert.deepEqual(fullMsPages(r.calc),run().seededMs);
  } else assert.notDeepEqual(afterPayload,payload,'selected continuation does not retain the original cache');
  if(mirror) {
    const plain=new MK61();
    for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
      plain[name]=()=>{throw Error('Forbidden state setter: '+name);};
    install(plain,fixtures[1]);preparePayload('8.7654321E-91',plain);
    prepareSelector(plain,{selector:4});finishSelector(plain,{selector:4});
    aligned(plain);plain.pressSequence(keys);aligned(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(r.calc),'complete unobserved native mirror');
  }
  return {keys,safe,first8C:first8C<0?null:events[first8C].command,
    firstEE:firstEE<0?null:events[firstEE].command,
    first8DRTail:first8D<0?null:events[first8D].r.slice(33,36),
    first8DSTTail:first8D<0?null:events[first8D].st.slice(33,36),
    originalCacheAtEnd:safe,observerIndependent:mirror,partialK2:false};
}
if(require.main===module) {
  if(process.argv.includes('--verbose')) console.log(JSON.stringify(extension(['F','Сx',',']).report));
  else {
    console.log(JSON.stringify(check(['F','Сx','F','ВП'],{safe:true,mirror:true})));
    for(const keys of [['F','Сx',','],['F','Сx','В↑'],['F','Сx','ВП'],
      ['F','Сx','4'],['F','Сx','↔'],['F','Сx','F','В↑']])
      console.log(JSON.stringify(check(keys)));
    console.log('PASS: seven selected native extensions; one complete unobserved safe-extension mirror. '+
      'No keyboard-completeness or partial-K2 exclusion is claimed.');
  }
}
module.exports={extension,check,lane,compact};
