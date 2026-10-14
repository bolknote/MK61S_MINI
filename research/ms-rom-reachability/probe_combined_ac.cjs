#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {trace}=require('./probe_ee_ring_source.cjs');
const {prepareCombined,finishCombined,isSignature}=require('./check_ac_signature_keyboard.cjs');
const extraIps='A9 AD DD D6 2F 20 21 22 36 37 38 06 07 6D 6F 60 25 26 C7 C8 6E 61 62 3A 63'
  .split(' ').map(v=>parseInt(v,16));

function run({counter=null}={}) {
  const calc=prepareCombined({counter});
  const result=trace(calc,finishCombined,{extraIps,fullState:true});
  const read=result.events.find(e=>e.ip===0xEE && e.raw==='600010000003' &&
    result.events.some(ac=>isSignature(ac) && ac.acNumber===e.acNumber));
  assert.ok(read,'joint AC signature AND actual EE word in one keyboard execution');
  const ac=result.events.find(e=>e.ip===0xAC && e.acNumber===read.acNumber);
  const expected='AC E2 E5 E6 ED EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A '+
    'E4 DE D6 E5 E6 E9 AD A9 93 94 95 98 9A E5 E6 E9 AD A5 1F 18 1B 1D 2E';
  assert.deepEqual(ac.route.slice(0,42),expected.split(' ').map(v=>parseInt(v,16)));
  const tail=result.events.filter(e=>e.command>=read.command && e.acNumber===read.acNumber);
  assert.ok(tail.some(e=>e.ip===0xDD && e.nextIp===0xD6));
  assert.deepEqual(result.primitives,counter===1?[0xC8,0xC8,0xC8]:[]);
  return {result,ac,read,tail,calc};
}

if(require.main===module) {
  const witness=run({counter:process.argv.includes('--counter-one')?1:null});
  if(process.argv.includes('--json')) {
    const {calc,...serializable}=witness;
    console.log(JSON.stringify(serializable));
  }
  else {
    console.log('PASS: actual AC/A9 high-mode L2 route; C8 count: '+witness.result.primitives.length);
    console.log(JSON.stringify({ac:witness.ac,read:witness.read}));
    for(const e of witness.tail.filter(e=>e.ip!==0xEE && e.ip!==0xDE))
      console.log(JSON.stringify({ip:e.ip.toString(16),next:e.nextIp?.toString(16),
        command:e.command,pc:e.pc.toString(16),r0:e.r0,r1:e.r1,r2:e.r2,
        r25:e.r[25],r26:e.r[26],r29:e.r[29],r32:e.r[32],r35:e.r35,r38:e.r[38],
        sp:e.sp,s:e.s,s1:e.s1,l:e.l,t:e.t,keys:[e.keyX,e.keyY],raw:e.raw}));
  }
}
module.exports={run,extraIps};
