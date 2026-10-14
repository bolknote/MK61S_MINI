#!/usr/bin/env node
'use strict';
// Passive ST[34] provenance audit; calculator state changes only through keys.
const assert = require('node:assert/strict');
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
const {prepareCombined,finishCombined,installArithmetic,rawMemoryRegister,
  finishSignature700,registerKey}=require('./check_ac_signature_keyboard.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {install,fixtures}=require('./check_partial_k2_program_scan.cjs');

function prepareSelector(calc,{selector=7,lowDigit=3}={}) {
  if(selector===7) return prepareCombined({calc,counter:1,lowDigit});
  assert.ok(Number.isInteger(selector)&&selector>=0&&selector<=14&&selector!==2);
  installArithmetic(calc,{input:'1E75',multiplier:'1.000000'+lowDigit,store:selector});
  calc.pressSequence(['В/О','С/П']).runFrames(12);aligned(calc);
  assert.equal(rawMemoryRegister(calc,selector),'60001000000'+lowDigit);
  calc.inputNumber('1',{clear:true}).pressSequence(['X→П','2']);
  installArithmetic(calc,{input:'1E87',multiplier:'1.0000005E4'});
  assert.equal(rawMemoryRegister(calc,selector),'60001000000'+lowDigit);
  return calc;
}

function finishSelector(calc,{selector=7,phaseOffset=0,settleFrames=4,signatureAddress='58'}={}) {
  calc.runFrames(phaseOffset);
  if(signatureAddress==='58') {
    if(selector===7) finishCombined(calc,{settleFrames});
    else {finishSignature700(calc,{settleFrames});calc.pressSequence(['П→X',registerKey(selector)]).runFrames(8);}
  } else {
    assert.match(signatureAddress,/^\d{2}$/);
    calc.pressSequence(['В/О','С/П']).runFrames(12);
    calc.pressSequence(['F','/-/']);
    calc.pressSequence(['F','ВП']).runFrames(settleFrames);
    calc.press('В↑').runFrames(settleFrames);
    calc.pressSequence(['F','/-/']).runFrames(settleFrames);
    calc.pressSequence(['БП',...signatureAddress]).runFrames(settleFrames);
    calc.pressSequence(['БП',...signatureAddress]).runFrames(settleFrames);
    calc.pressSequence(['П→X',registerKey(selector)]).runFrames(8);
  }
  return calc;
}

function run({payload='8.7654321E-91', lowDigit=3,phaseOffset=0,settleFrames=4,selector=7,signatureAddress='58',allowNoC8=false}={}) {
  const calc = new MK61(), chip=calc.ik1302;
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw Error('Forbidden state setter: '+name);};
  let stage='install',command=-1,ip,firstC8=null,beforeC8=[],seededMs;
  const operations=[],changes=[],boundaries=[],stages=[],recent=[],primitives=[];
  const micro=chip.executeMicroOrder, tick=chip.tick;
  chip.tick=function(){
    if(this.tickIndex===0) {
      command++; ip=this.r[36]+16*this.r[39];
      if(ip===0xC7||ip===0xC8) primitives.push({ip,command});
      if(stage.startsWith('finishCombined')) {
        recent.push({stage,command,ip,r:this.r.slice(),st:this.stack.slice(),m:this.memory.slice(),
          s:this.s,s1:this.s1,l:this.l,t:this.t,carry:this.carry,keyX:this.keyX,keyY:this.keyY});
        if(recent.length>700) recent.shift();
      }
      if(ip===0xC8&&firstC8===null) {
        firstC8={stage,command,ip,st:this.stack.slice(),r:this.r.slice()};
        beforeC8=recent.slice();
      }
      if(ip===0xAC||ip===0xC8||ip===0xC7) boundaries.push({stage,command,ip,
        st32:this.stack[32],st33:this.stack[33],st34:this.stack[34],st35:this.stack[35],
        r1:this.r[1],r34:this.r[34],r35:this.r[35]});
    }
    return tick.call(this);
  };
  chip.executeMicroOrder=function(number,acc){
    const touches=number>=32&&number<=34&&[32,33,34].includes(this.tickIndex);
    const before=touches?this.stack.slice(32,37):null;
    const record=touches?{stage,command,ip,tick:this.tickIndex,number,
      before,sigma:acc.sigma,r32:this.r[32],r33:this.r[33],r34:this.r[34],r35:this.r[35],
      s:this.s,s1:this.s1}:null;
    const ret=micro.call(this,number,acc);
    if(touches) {
      record.after=this.stack.slice(32,37);operations.push(record);
      if(before[2]!==record.after[2]) changes.push(record);
    }
    return ret;
  };
  const step=(name,action)=>{stage=name;action();stages.push({stage,command,ip,
    st32:chip.stack[32],st33:chip.stack[33],st34:chip.stack[34],st35:chip.stack[35]});};
  try {
    step('install',()=>install(calc,fixtures[1]));
    if(payload!==null) step('payload',()=>preparePayload(payload,calc));
    seededMs=fullMsPages(aligned(calc));
    step('prepareCombined',()=>prepareSelector(calc,{selector,lowDigit}));
    step('finishCombined',()=>finishSelector(calc,{selector,phaseOffset,settleFrames,signatureAddress}));
    aligned(calc);
  } finally {chip.executeMicroOrder=micro;chip.tick=tick;}
  if(allowNoC8&&firstC8===null)
    return {calc,stages,firstC8,boundaries,operations,changes,recent,beforeC8,seededMs,primitives};
  assert.ok(firstC8);
  assert.equal(firstC8.st[34],15,'the native C8 entry has ST34=F');
  assert.equal(chip.stack[34],15,'the native three-byte reader preserves ST34');
  assert.equal(chip.stack[33],selector,'the native selector remains in ST33 after the reader');
  assert.deepEqual(fullMsPages(calc),seededMs,'all 56 seeded Ms bytes survive');
  assert.equal(changes.filter(o=>o.command>=firstC8.command).length,0,
    'there are no ST34 changes anywhere after C8 in this reader');
  return {calc,stages,firstC8,boundaries,operations,changes,recent,beforeC8,seededMs,primitives};
}

if(require.main===module){
  const r=run();
  if(process.argv.includes('--proof-input')) {
    const ac=r.beforeC8.findLastIndex(e=>e.ip===0xAC);
    console.log(JSON.stringify({events:r.beforeC8.slice(ac)}));
  } else {
    const ac=r.beforeC8.findLast(e=>e.ip===0xAC),last=r.changes.findLast(o=>o.command<r.firstC8.command);
    assert.equal(ac.st[32],15);
    assert.equal(last.ip,0x95);
    assert.equal(last.before[3],15);
    assert.equal(last.after[2],15);
    console.log(JSON.stringify({scope:'keyboard-only native ST34 provenance',
      ac:{command:ac.command,st32:ac.st[32],st34:ac.st[34]},
      lastST34Write:{command:last.command,ip:'95',source:'ST35 before 95',value:last.after[2]},
      C8:{command:r.firstC8.command,st34:r.firstC8.st[34]},
      finalST34:r.calc.ik1302.stack[34],noST34ChangesAfterC8:true}));
    console.log('PASS: native AC source F reaches C8 and survives the three-byte reader.');
  }
}
module.exports={run,prepareSelector,finishSelector};
