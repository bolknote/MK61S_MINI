#!/usr/bin/env node
'use strict';
// Follow C8 data after a keyboard-only, explicitly separate test-data setup.
// The historical pustyshka writer supplies a known Ms word; it is NOT the
// operation under investigation. No host state setters or ROM edits are used.
const assert=require('node:assert/strict');
const path=require('node:path');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {prepareCombined,finishCombined,rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const root=process.env.MK61_REFERENCE_ROOT||path.resolve(__dirname,'../../..','MK-61');
const {EXTRA,extraWords}=require(path.join(root,'tests/emulator/probe-pustyshka-capacity.cjs'));
const ips=Array.from({length:256},(_,i)=>i);
const hex=a=>a.map(v=>v.toString(16).toUpperCase()).join('');

function fullMsPages(calc) {
  assert.equal(calc.ir2a.tickIndex,84);
  return Object.fromEntries(Object.entries(EXTRA).map(([name,[chip,end]])=>
    [name,hex(Array.from({length:14},(_,i)=>calc.memoryForChip(chip)[end+6-3*i]))]));
}

function inputLiteral(calc,value) {
  const match=String(value).toUpperCase().match(/^(-?)(\d+(?:[.,]\d+)?)(?:E([+-]?\d+))?$/);
  assert.ok(match,'explicit decimal test data required');
  calc.inputNumber(match[2],{clear:true});
  if(match[1]) calc.press('/-/');
  if(match[3]!==undefined) {
    calc.press('ВП').inputNumber(String(Math.abs(Number(match[3]))));
    if(Number(match[3])<0) calc.press('/-/');
  }
}

function preparePayload(value,calc=new MK61()) {
  const values=Array.isArray(value)?value:[value,'222','333'];
  assert.ok(values.length>=3&&values.length<=4);
  // The established ROM writer, entered through keys, with STOP in place of
  // its usual subroutine return. It restores the ordinary scanner each time.
  calc.pressSequence(['В/О','F','ВП','X→П','9','Сx','K','Сx','K','8','↔',
    'П→X','9','F',',','Сx','В↑','В↑','В↑','+','С/П','F','/-/','В/О']);
  assert.deepEqual(Array.from({length:13},(_,i)=>calc.readCommand(i)),
    [0x49,0x0D,0x3A,0x35,0x14,0x69,0x25,0x0D,0x0E,0x0E,0x0E,0x10,0x50]);
  // Three writes fill W,V,U; four also fill Q. The last input becomes U.
  const expected=[];
  for(const v of values) {
    inputLiteral(calc,v);
    calc.pressSequence(['В/О','С/П']).runFrames(20);
    assert.equal(calc.programCounter(),'13');
    aligned(calc);
    expected.unshift(rawMemoryRegister(calc,9).toLowerCase());
  }
  aligned(calc);
  const words=extraWords(calc);
  assert.deepEqual(Object.values(words).slice(0,values.length),expected);
  // Remove the temporary writer by programming zeroes, not by an import API.
  calc.pressSequence(['В/О','F','ВП',...Array(13).fill('0'),'F','/-/','В/О',
    'Сx','X→П','9']);
  aligned(calc);
  return calc;
}

function run(value=null,options={}) {
  const calc=new MK61(),chip=calc.ik1302,originalTick=chip.tick;
  const wholePrimitives=[];
  // These APIs are forbidden even during the known-data setup.
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw new Error('Forbidden state setter: '+name);};
  chip.tick=function() {
    if(this.tickIndex===0) {
      const ip=this.r[36]+16*this.r[39];
      if(ip===0xC7||ip===0xC8) {
        wholePrimitives.push(ip);
        if(ip===0xC8 && wholePrimitives.length===1) options.onFirstC8?.(calc);
      }
    }
    return originalTick.call(this);
  };
  let before,fullBefore,programBefore,result;
  try {
    // Optional explicit test fixture, installed through ordinary keys by the
    // caller. The forbidden import/state-setter guards above already apply.
    options.prepareProgram?.(calc);
    if(value!==null) preparePayload(value,calc);
    const seeded=extraWords(calc),fullSeeded=fullMsPages(calc);
    prepareCombined({calc,counter:1});
    before=extraWords(calc);fullBefore=fullMsPages(calc);
    assert.deepEqual(before,seeded,'C8 setup must preserve the known Ms payload');
    assert.deepEqual(fullBefore,fullSeeded,'C8 setup must preserve all 56 Ms bytes');
    assert.deepEqual(wholePrimitives,[],'no C7/C8 in the payload or witness preparation');
    programBefore=Array.from({length:105},(_,i)=>calc.readCommand(i));
    result=trace(calc,c=>{
      c.runFrames(options.phaseOffset||0);
      finishCombined(c,options);
    },{extraIps:ips,fullState:true,startIp:0xC8});
  } finally {chip.tick=originalTick;}
  assert.deepEqual(wholePrimitives,result.primitives);
  const first=result.events.find(e=>e.ip===0xC8);
  assert.ok(first,'the same keyboard witness still reaches C8');
  aligned(calc);
  const programAfter=Array.from({length:105},(_,i)=>calc.readCommand(i));
  const after=extraWords(calc),fullAfter=fullMsPages(calc);
  const tail=result.events.filter(e=>e.command>=first.command);
  return {calc,result,first,tail,report:{value,before,after,fullBefore,fullAfter,
    display:calc.displayText(),pc:calc.programCounter(),
    retainedMantissa:hex(Array.from({length:8},(_,i)=>calc.ik1302.r[7+3*i])),
    primitives:result.primitives.map(v=>v.toString(16).toUpperCase()),
    reads:tail.filter(e=>e.ip===0xC8).map(e=>({command:e.command,slot:e.slot,
      word:hex(e.m.filter((_,i)=>i%3===1))})),
    continuation:tail.slice(0,32).map(e=>({command:e.command,
      ip:e.ip.toString(16).toUpperCase(),next:e.nextIp.toString(16).toUpperCase(),
      slot:e.slot,r1:hex(e.r.filter((_,i)=>i%3===1))})),
    programChanges:programAfter.flatMap((v,i)=>v===programBefore[i]?[]:
      [{address:i,before:programBefore[i],after:v}]),
    registers:Object.fromEntries(['x','y','z','t','0','1','2','7','8','9'].map(n=>
      [n,calc.readRegister(n,{syncPhase:false})]))}};
}

if(require.main===module) console.log(JSON.stringify(run(process.argv[2]||null).report,null,2));
module.exports={run,preparePayload,fullMsPages,inputLiteral};
