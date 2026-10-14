#!/usr/bin/env node
'use strict';
// A ROM-directed extension of the byte reader, not a scan of key sequences.
// Loaded decimal PC 90+e minus 3 selects 87+e. For exponent -91, e=0;
// after each read it increments until the units digit equals mantissa sign 0.
// Thus the predicted addresses are 87,88,89, each fetched without execution.
const assert=require('node:assert/strict');
const {run,preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {prepareCombined,finishCombined}=require('./check_ac_signature_keyboard.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const lane=(a,n)=>a.filter((_,i)=>i%3===n);
const hex=a=>a.map(n=>n.toString(16).toUpperCase()).join('');
const value='8.7654321E-91';
const fixtures=[
  {name:'digits',bytes:[1,2,3,4,5,6,7],keys:['1','2','3','4','5','6','7']},
  {name:'raw_hex',bytes:[1,2,3,0xA3,0xD4,0xB5,7],
    keys:['1','2','3','K','ПП','3','K','П→X','4','K','X→П','5','7']},
];

function install(calc,f) {
  calc.pressSequence(['БП','8','4','F','ВП',...f.keys,'F','/-/','В/О']);
  assert.deepEqual(Array.from({length:7},(_,i)=>calc.readCommand(84+i)),f.bytes);
}

function capture(f=fixtures[0],options={}) {
  const result=run(value,{...options,prepareProgram:c=>install(c,f)});
  const events=result.tail,swaps=events.filter(e=>e.ip===0xC9);
  assert.equal(events.filter(e=>e.ip===0xC8).length,1);
  assert.equal(swaps.length,6,'three byte reads, each with a restoring C9 pair');
  const read=[];
  for(let i=0;i<3;i++) {
    const first=swaps[2*i],second=swaps[2*i+1];
    assert.equal(first.slot,'Y');assert.equal(second.slot,'Y');
    const after=events.find(e=>e.command===second.command+1);
    assert.equal(after.ip,6);
    assert.deepEqual(lane(second.r,1),lane(first.m,2),'each pair returns its entire program');
    assert.equal(after.r[30]+16*after.r[33],f.bytes[3+i]);
    read.push({address:87+i,code:after.r[30]+16*after.r[33]});
  }
  assert.deepEqual(result.report.fullAfter,result.report.fullBefore,'all 56 Ms bytes held');
  assert.deepEqual(result.report.programChanges,[{address:70,before:0,after:14}]);
  const r=result.calc.ik1302.r;
  const cache=[0,9,18].map(n=>r[n]+16*r[n+3]);
  assert.deepEqual(cache,f.bytes.slice(3,6),'all THREE raw bytes coexist after the call');
  for(const n of [6,15,24])assert.equal(r[n],15,'three fixed F separators');
  const state=machineSnapshot(result.calc),beforeIdle=digest(result.calc);
  result.calc.runFrames(60);assert.equal(digest(result.calc),beforeIdle);
  const plain=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    plain[name]=()=>{throw Error('Forbidden host setter: '+name);};
  install(plain,f);preparePayload(value,plain);prepareCombined({calc:plain,counter:1});
  plain.runFrames(options.phaseOffset||0);finishCombined(plain,options);aligned(plain);
  assert.deepEqual(machineSnapshot(plain),state,'fresh complete unobserved mirror');
  assert.deepEqual(fullMsPages(plain),result.report.fullBefore);
  return {result,swaps,state,report:{name:f.name,options,read,cache,
    cacheA:hex(lane(r,0).slice(0,12)),allMsHeld:true,programReturned:true,
    observerIndependent:true,partialK2:false}};
}

function proofInput() {
  const c=capture(),events=c.result.tail;
  const start=events.indexOf(c.swaps[0]),last=events.indexOf(c.swaps.at(-1));
  const end=events.findIndex((e,i)=>i>last&&e.ip===0x33);
  assert.ok(end>last);
  const selected=events.slice(start,end+1);
  for(let i=1;i<selected.length;i++)assert.equal(selected[i].command,selected[i-1].command+1);
  return {scope:'three-byte local reader; not a program-to-Ms write',events:selected,
    programSlot:'Y',packetTetras:[4,5,6,7,8,9]};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(proofInput()));
  else {
    for(const [f,options] of [[fixtures[0],{}],[fixtures[1],{}],
      [fixtures[1],{phaseOffset:1}],[fixtures[1],{phaseOffset:2,settleFrames:10}]])
      console.log(JSON.stringify(capture(f,options).report));
    console.log('PASS: four native three-byte readers, four fresh complete-state mirrors. '+
      'Program bytes 87..89 are retained simultaneously; no Ms write or partial K2.');
  }
}
module.exports={capture,proofInput,fixtures,install};
