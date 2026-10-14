#!/usr/bin/env node
'use strict';
// Structural construction: a register-7 recall supplies R35=7, while a
// real order-700 word avoids the ordinary cleanup that erases the saved tail.
// All preparation uses keys on the unchanged, three-chip reference model.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {installArithmetic,rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const hex=n=>n.toString(16).toUpperCase();

function prepare({payloadRegister=4,payloadLowDigit=1,values=null}={}) {
  assert.ok(Number.isInteger(payloadRegister)&&payloadRegister>=1&&payloadRegister<=9&&payloadRegister!==7);
  assert.ok(Number.isInteger(payloadLowDigit)&&payloadLowDigit>=0&&payloadLowDigit<=9);
  const calc=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw new Error('Forbidden state setter: '+name);};
  if(values!==null) preparePayload(values,calc);
  installArithmetic(calc,{input:'1E75',multiplier:'1.000000'+payloadLowDigit,store:payloadRegister});
  calc.pressSequence(['В/О','С/П']).runFrames(12);
  aligned(calc);
  assert.equal(rawMemoryRegister(calc,payloadRegister),'60001000000'+payloadLowDigit);
  installArithmetic(calc,{input:'1E87',multiplier:'1.0000005E4',store:7});
  return aligned(calc);
}

function finish(calc,{payloadRegister=4,settleFrames=8,phaseOffset=0}={},record=()=>{}) {
  assert.ok(Number.isInteger(settleFrames)&&settleFrames>=1);
  assert.ok(Number.isInteger(phaseOffset)&&phaseOffset>=0&&phaseOffset<=2);
  // Apply AFTER the observer binds its physical tags at phase 1; otherwise
  // aligned() would erase the distinction between the three starting phases.
  calc.runFrames(phaseOffset);
  const stages=[];
  const actions=[
    ['run',['В/О','С/П'],12],
    ['auto',['F','/-/'],settleFrames],
    ['clear',['Сx'],settleFrames],
    ['seed-seven',['П→X','7'],settleFrames],
    ['save-seven',['F','/-/'],settleFrames],
    ['clear-again',['Сx'],settleFrames],
    ['address',['БП','В↑','0'],settleFrames],
    ['recall',['П→X',String(payloadRegister)],settleFrames],
  ];
  for(const [label,keys,frames] of actions) {
    record(label);
    calc.pressSequence(keys).runFrames(frames);
    const k=calc.ik1302;
    stages.push({label,pc:k.r[31]+16*k.r[34],ip:k.r[36]+16*k.r[39],
      r2:k.r[2],r35:k.r[35],s1:k.s1,tail:k.stack.slice(30,36)});
  }
  return stages;
}

function run(options={}) {
  const calc=prepare(options),beforeMs=fullMsPages(calc);
  let stage='',stages;
  const traced=trace(calc,c=>{stages=finish(c,options,label=>{stage=label;});},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      ringAt:e=>{e.stage=stage;return [0xEE,0xA8,0xA9,0x93].includes(e.ip);}});
  const es=traced.events,singles=[];
  for(let i=1;i<es.length-2;i++) if(es[i].ip===0xA8&&es[i].s1===14&&es[i-1].ip===0xEE) {
    const acIndex=es.findLastIndex((e,j)=>j<i&&e.ip===0xAC);
    assert.ok(acIndex>=0);
    // Only E5 self-waits are suppressed; E6 self-loops and other operations
    // remain observable. This can be compared with the connected ROM proof.
    const route=es.slice(acIndex,i+2).filter((e,j,rows)=>!(e.ip===0xE5&&rows[j-1]?.ip===0xE5));
    singles.push({ac:es[acIndex],ee:es[i-1],swap:es[i],exit:es[i+1],after:es[i+2],route,
      writes:traced.writes.filter(w=>w.command===es[i].command)});
  }
  aligned(calc);
  return {calc,stages,traced,singles,beforeMs,afterMs:fullMsPages(calc)};
}

if(require.main===module) {
  const result=run({payloadRegister:Number(process.argv[2]||4)});
  console.log(JSON.stringify({stages:result.stages,singles:result.singles.map(s=>({
    command:s.swap.command,source:s.ee.slot,target:s.swap.slot,sourceWord:s.ee.raw,
    oldTarget:s.swap.raw,return:hex(s.exit.nextIp),routeLength:s.route.length,
    route:s.route.map(e=>hex(e.ip)).join(' ')})),msUnchanged:
    JSON.stringify(result.beforeMs)===JSON.stringify(result.afterMs),display:result.calc.displayText()},null,2));
}
module.exports={prepare,finish,run};
