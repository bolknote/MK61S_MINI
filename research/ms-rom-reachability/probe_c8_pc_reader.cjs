#!/usr/bin/env node
'use strict';
// Read sign + the units digit of a positive exponent through the PC produced
// by actual C8, then dispatch to an ordinary numeric result. NOT a full reader.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {prepareStored600,finishCombined,rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {snapshot}=require('./paused_keyboard_state.cjs');
const allIps=Array.from({length:256},(_,i)=>i);
const listing=calc=>Array.from({length:105},(_,i)=>calc.readCommand(i));

function machineSnapshot(calc) {
  return Object.fromEntries(['ik1302','ik1303','ik1306','ir2a','ir2b'].map(name=>{
    const c=calc[name];
    return [name,{...(c.r?snapshot(c):{m:c.memory.slice()}),
      tick:c.tickIndex,input:c.input,output:c.output,keyX:c.keyX,keyY:c.keyY}];
  }));
}

function installReadout(calc) {
  const program=Array(105).fill(0);
  program[2]=0;program[3]=0x50;
  // Entering at 10n+2 reads n. Entering one step earlier executes EXP,
  // so the same digit produces 1E+n instead (X is set to 1 before RUN).
  for(let n=1;n<=9;n++) program.splice(10*n+1,3,0x0C,n,0x50);
  program.splice(101,4,0x0C,1,0,0x50); // final negative case: 1E10
  program.splice(4,6,0x22,0x22,0x22,0x60,0x12,0x50); // order-700 preparation
  const keycode=code=>code<10?[String(code)]:({
    12:['ВП'],18:['*'],34:['F','*'],80:['С/П'],96:['П→X','0'],
  }[code]);
  calc.pressSequence(['В/О','F','ВП',...program.flatMap(code=>{
    const keys=keycode(code);assert.ok(keys,`no key recipe for ${code}`);return keys;
  }),'F','/-/','В/О']);
  assert.deepEqual(listing(calc),program);
  return program;
}

function read(value,{phaseOffset=0,settleFrames=4,readoutIdle=0}={}) {
  const calc=new MK61(),ch=calc.ik1302,originalTick=ch.tick;
  const wholePrimitives=[];
  let atFirstC8;
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw new Error('Forbidden state setter: '+name);};
  ch.tick=function() {
    if(this.tickIndex===0) {
      const ip=this.r[36]+16*this.r[39];
      if(ip===0xC7||ip===0xC8) wholePrimitives.push(ip);
      if(ip===0xC8 && !atFirstC8) atFirstC8=machineSnapshot(calc);
    }
    return originalTick.call(this);
  };
  let seeded,program,result,afterReadout;
  try {
    preparePayload(value,calc);seeded=fullMsPages(calc);
    prepareStored600(calc);
    assert.equal(rawMemoryRegister(calc,7),'600010000003');
    program=installReadout(calc);
    calc.inputNumber('1',{clear:true}).pressSequence(['X→П','2']);
    calc.inputNumber('1.0000005E4',{clear:true}).pressSequence(['X→П','0']);
    calc.inputNumber('1E87',{clear:true});aligned(calc);
    assert.deepEqual(fullMsPages(calc),seeded);
    assert.deepEqual(wholePrimitives,[]);
    result=trace(calc,c=>{
      c.runFrames(phaseOffset);
      finishCombined(c,{settleFrames,startAddress:'04'});
    },{extraIps:allIps,fullState:true,startIp:0xC8});
    assert.ok(result.primitives.length,'relocated preparation must still execute C8');
    const pc=calc.programCounter(),display=calc.displayText();
    aligned(calc);
    assert.deepEqual(fullMsPages(calc),seeded);
    program[70]=0x0E; // deliberate ENTER in the original order-700 witness
    assert.deepEqual(listing(calc),program);
    const retained=Array.from({length:8},(_,i)=>calc.ik1302.r[7+3*i]);
    afterReadout=trace(calc,()=>{
      for(const key of ['ШГ→','ШГ→','П→X','2','F','/-/','С/П'])
        calc.press(key).runFrames(readoutIdle);
      calc.runFrames(20);
      for(const key of ['X→П','8']) calc.press(key).runFrames(readoutIdle);
      calc.runFrames(4);
    });
    aligned(calc);
    assert.deepEqual(afterReadout.primitives,[],'no second C8 during numeric readout');
    assert.deepEqual(fullMsPages(calc),seeded,'numeric readout preserves all Ms pages');
    assert.deepEqual(listing(calc),program,'numeric readout preserves the program');
    const beforeIdle=digest(calc);calc.runFrames(60);
    assert.equal(digest(calc),beforeIdle,'result must be stable');
    return {calc,result,afterReadout,atFirstC8,report:{value,pc,display,
      finalDisplay:calc.displayText(),x:calc.readRegister('x',{syncPhase:false}),
      p8:rawMemoryRegister(calc,8),retained,
      reads:result.events.filter(e=>e.ip===0xC8).map(e=>({
        slot:e.slot,word:e.m.filter((_,i)=>i%3===1).map(v=>v.toString(16)).join('')})),
      wholePrimitives:wholePrimitives.map(ip=>ip.toString(16))}};
  } finally {ch.tick=originalTick;}
}

if(require.main===module) console.log(JSON.stringify(read(process.argv[2]||'1.0234567E30').report,null,2));
module.exports={read,installReadout,machineSnapshot};
