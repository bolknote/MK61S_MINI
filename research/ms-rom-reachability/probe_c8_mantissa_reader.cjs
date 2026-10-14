#!/usr/bin/env node
'use strict';
// Keyboard-only extraction of all eight retained C8 mantissa digits.
// The host reads the actual display; it does not feed decoded data back in.
const assert=require('node:assert/strict');
const {run,fullMsPages}=require('./probe_c8_payload.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const allIps=Array.from({length:256},(_,i)=>i);
const listing=calc=>Array.from({length:105},(_,i)=>calc.readCommand(i));

function readMantissa(value,{readoutIdle=8,fullTrace=false,...setupOptions}={}) {
  let atFirstC8;
  const result=run(value,{...setupOptions,onFirstC8:calc=>{
    atFirstC8=machineSnapshot(calc);
  }});
  const {calc}=result;
  aligned(calc);
  const program=listing(calc),ms=fullMsPages(calc);
  assert.deepEqual(ms,result.report.fullBefore,'C8 itself preserves the seeded Ms');
  const initialDisplay=calc.displayText(),pairs=[];
  const readout=trace(calc,()=>{
    for(let n=0;n<4;n++) {
      calc.press('В/О').runFrames(readoutIdle);
      aligned(calc);
      const cells=calc.displayCells();
      const [hi,lo]=cells.slice(-2).map(c=>c.digit);
      assert.ok(hi<=10 && lo<=9,'display must contain a decimal pair or 100');
      const encoded=10*hi+lo;
      assert.ok(encoded>=1 && encoded<=100,'one-based pair range');
      pairs.push({display:calc.displayText(),counter:calc.programCounter(),
        encoded,decoded:String(encoded-1).padStart(2,'0'),
        r:calc.ik1302.r.slice(),stateDigest:digest(calc)});
      assert.deepEqual(fullMsPages(calc),ms,'each extraction preserves all Ms');
      assert.deepEqual(listing(calc),program,'each extraction preserves the listing');
      const beforeIdle=digest(calc);
      calc.runFrames(60);
      assert.equal(digest(calc),beforeIdle,'each displayed pair remains stable');
    }
  },fullTrace?{extraIps:allIps,fullState:true}:{});
  assert.deepEqual(readout.primitives,[],'extracting digits does not invoke another C8/C7');
  return {calc,result,readout,atFirstC8,report:{value,initialDisplay,
    mantissa:pairs.map(p=>p.decoded).join(''),pairs,
    reads:result.report.reads,readoutPrimitives:readout.primitives}};
}

if(require.main===module) {
  const {report}=readMantissa(process.argv[2]||'1.2345678E30');
  console.log(JSON.stringify({...report,pairs:report.pairs.map(({r,...p})=>p)},null,2));
}
module.exports={readMantissa};
