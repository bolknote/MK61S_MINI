#!/usr/bin/env node
'use strict';
// Structural neighbor of the C8 witness: DD writes R38=lowDigit+1, and
// 60 chooses ((R38+8)&15):8. Digit 1 therefore targets A8 rather than C8.
// Every modification of the reference calculator is an ordinary key/frame.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {prepareCombined,finishCombined}=require('./check_ac_signature_keyboard.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const hex=a=>a.map(v=>v.toString(16).toUpperCase()).join('');

function run({lowDigit=1,values=null,phaseOffset=0,settleFrames=4,counter=1}={}) {
  const calc=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw new Error('Forbidden state setter: '+name);};
  if(values!==null)preparePayload(values,calc);
  aligned(calc);const seeded=fullMsPages(calc);
  prepareCombined({calc,counter,lowDigit});
  assert.deepEqual(fullMsPages(calc),seeded,'preparation must preserve every Ms tetrade');
  const before=fullMsPages(calc);
  const traced=trace(calc,c=>{
    c.runFrames(phaseOffset);finishCombined(c,{settleFrames});
  },{extraIps:[0x60,0x61,0x3A,0x06,0x07,0x6D,0xA8,0xA9,0x6E,0xDD,0xD4,0xD6,
              0x26,0x28,0x2A,0x63,0xCC,0xCD,0xC9,0x7E,0x75,0x7C],fullState:true,allWrites:true,
    ringAt:e=>(e.ip===0xA8||e.ip===0xA9)&&e.s1===0&&e.sp[0]===0x6E});
  const entries=traced.events.flatMap((event,index)=>{
    if(event.ip!==0x60||event.nextIp!==0xA8)return [];
    const body=traced.events.slice(index+1).filter(e=>e.command<=event.command+10);
    const swaps=body.filter(e=>e.ip===0xA8);
    const exit=body.find(e=>e.ip===0xA9);
    if(swaps.length===8&&exit) {
      assert.deepEqual(swaps.map(e=>e.s1),[0,2,4,6,8,10,12,14]);
      assert.equal(exit.nextIp,0x6E);
      const expected=structuredClone(swaps[0].ring);
      let carried=swaps[0].r.slice(0,36).filter((_,i)=>i%3===0);
      for(const swap of swaps) {
        assert.deepEqual(swap.r.slice(0,36).filter((_,i)=>i%3===0),carried);
        const old=expected[swap.slot].slice(1,36).filter((_,i)=>i%3===0);
        for(let i=0;i<12;i++)expected[swap.slot][1+3*i]=carried[i];
        carried=old;
      }
      assert.deepEqual(exit.r.slice(0,36).filter((_,i)=>i%3===0),carried);
      // All 630 ring tetras, not just the display or eight mantissas.
      assert.deepEqual(exit.ring,expected,'eight exact exchanges, no other ring mutation in this block');
    }
    return [{gate:{command:event.command,slot:event.slot,r38:event.r[38],s1:event.s1},
      complete:swaps.length===8&&!!exit,
      body:body.map(e=>({ip:e.ip,command:e.command,slot:e.slot,s1:e.s1,nextIp:e.nextIp,
        a:hex(e.r.slice(0,36).filter((_,i)=>i%3===0)),
        m2:hex(e.m.filter((_,i)=>i%3===1))}))}];
  });
  aligned(calc);
  return {calc,traced,report:{lowDigit,values,counter,entries,before,after:fullMsPages(calc),
    display:calc.displayText(),pc:calc.programCounter(),
    relevantGates:traced.events.filter(e=>e.ip===0x60).map(e=>
      ({command:e.command,slot:e.slot,r38:e.r[38],nextIp:e.nextIp}))}};
}

if(require.main===module) {
  const result=run({lowDigit:Number(process.argv[2]||1)});
  const r=result.report;
  console.log(JSON.stringify({...r,entryCount:r.entries.length,entries:r.entries.slice(0,2),
    relevantGates:r.relevantGates.slice(0,12)},null,2));
}
module.exports={run};
