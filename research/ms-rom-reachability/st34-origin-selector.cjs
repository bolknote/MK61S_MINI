#!/usr/bin/env node
'use strict';
// ROM-derived selector relocation: retain numeric 4 in ST33 alongside the
// raw byte cache. It is preparation for a further push, not a partial K2.
const assert=require('node:assert/strict');
const {run,prepareSelector,finishSelector}=require('./st34-origin-trace.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fixtures,install}=require('./check_partial_k2_program_scan.cjs');

function check(options={}) {
  const settings={...options,selector:4},observed=run(settings),c=observed.calc;
  const cache=calc=>[0,9,18].map(n=>calc.ik1302.r[n]+16*calc.ik1302.r[n+3]);
  assert.deepEqual(cache(c),[0xA3,0xD4,0xB5]);
  assert.deepEqual(c.ik1302.stack.slice(33,36),[4,15,5]);
  const firstAC=observed.beforeC8.findLast(e=>e.ip===0xAC);
  assert.deepEqual([firstAC.r[1],firstAC.st[32],firstAC.st[35],firstAC.r[35]],[5,15,9,4]);
  const plain=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    plain[name]=()=>{throw Error('Forbidden state setter: '+name);};
  install(plain,fixtures[1]);preparePayload('8.7654321E-91',plain);
  const seeded=fullMsPages(plain);
  prepareSelector(plain,settings);finishSelector(plain,settings);aligned(plain);
  assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'fresh unobserved full-machine mirror');
  assert.deepEqual(fullMsPages(plain),seeded,'all 56 Ms bytes held');
  assert.deepEqual(seeded,observed.seededMs);
  const report={options,selector:4,C8Reached:true,cache:cache(c),
    finalST33to35:c.ik1302.stack.slice(33,36),all56MsBytesHeld:true,observerIndependent:true,
    partialK2:false};
  console.log(JSON.stringify(report));
  return {observed,report};
}

if(require.main===module) {
  check();check({phaseOffset:2,settleFrames:10});
  console.log('PASS: two native selector-4 three-byte readers and two complete unobserved mirrors.');
}
module.exports={check};
