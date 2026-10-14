#!/usr/bin/env node
'use strict';
// Investigate the saved-state requirements of EE -> A8(S1=E).
// Fixed ordinary keyboard actions only; tracing never changes the machine.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {prepareStored600,installArithmetic}=require('./check_ac_signature_keyboard.cjs');

function run({middle='signature',lastDigit=5,ending='stop',prefixNops=0,extraIps=[]}={}) {
  assert.ok(Number.isInteger(lastDigit)&&lastDigit>=0&&lastDigit<=9);
  const calc=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw new Error('Forbidden state setter: '+name);};
  prepareStored600(calc,1);
  installArithmetic(calc,{input:'1E87',multiplier:'1.000000'+lastDigit+'E4',prefixNops});
  if(ending==='condition7') {
    // Negative control: change the following opcode, not its position.
    assert.equal(prefixNops,0);
    calc.pressSequence(['БП','0','5','F','ВП','K','С/П','0','С/П','F','/-/','В/О']);
    assert.equal(calc.readCommand(5),0x70);
    assert.equal(calc.readCommand(6),0x50);
  } else assert.equal(ending,'stop');
  const stages=[];
  let stage='run';
  const actions=[
    ['run',['В/О','С/П'],12],
    ['auto',['F','/-/'],4],
    ...(middle==='signature'?[
      ['program',['F','ВП'],4],['enter',['В↑'],4],['auto-again',['F','/-/'],4],
    ]:middle==='enter'?[
      ['enter',['В↑'],4],
    ]:middle==='clear'?[
      ['clear',['Сx'],4],
    ]:middle==='program7'?[
      ['program',['F','ВП'],4],['opcode7',['K','С/П','0'],4],
      ['auto-again',['F','/-/'],4],['clear',['Сx'],4],
    ]:middle==='manual7'?[
      ['opcode7',['K','С/П','0'],4],['clear',['Сx'],4],
    ]:middle==='none'?[]:(()=>{throw new Error('Unknown middle');})()),
    ['address',['БП','В↑','0'],4],
    ['address-again',['БП','В↑','0'],4],
    ['recall',['П→X','7'],8],
  ];
  const traced=trace(aligned(calc),c=>{
    for(const [label,keys,frames] of actions) {
      stage=label;
      c.pressSequence(keys).runFrames(frames);
      const k=c.ik1302;
      stages.push({label,pc:k.r[31]+16*k.r[34],tail:k.stack.slice(27,36),
        r1:k.r[1],r2:k.r[2],r35:k.r[35]});
    }
  },{extraIps:[0xA7,0xE5,0xE6,0xE7,0xA8,0xA9,0xAD,0xDD,0xD4,0xD6,0xE0,...extraIps],
      fullState:true,ringAt:e=>{
        e.stage=stage;
        return e.ip===0xA8&&e.s1===14;
      }});
  const singles=traced.events.filter((e,i)=>e.ip===0xA8&&e.s1===14&&
    traced.events[i-1]?.ip!==0xA8);
  return {calc,traced,stages,singles};
}

if(require.main===module) {
  const r=run({middle:process.argv[2]||'signature',lastDigit:Number(process.argv[3]||5)});
  console.log(JSON.stringify({stages:r.stages,singles:r.singles,
    ac:r.traced.events.filter(e=>e.ip===0xAC).map(e=>({stage:e.stage,pc:e.pc,
      st32:e.st32,st35:e.st35,r1:e.r1,route:e.route})),
    display:r.calc.displayText()},null,2));
}
module.exports={run};
