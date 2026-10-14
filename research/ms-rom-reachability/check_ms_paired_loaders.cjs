#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_marked_return.cjs');
const {checkPairedPath}=require('./check_ms_upper_read2_exit.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const loadD=['K','П→X','Сx'],loadE=['K','П→X','В↑'];
for(const phaseOffset of [0,1,2]) {
  const r=p.run({phaseOffset,stress:true,traceFormatterExit:true,
    values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
    upperValues:['6.5432109E-23','-8.7654321E-17','333','444'],afterKeys:[loadD,loadD,loadE]});
  const es=r.traced.events,routes=[];
  assert.equal(r.afterRegisters[0],r.before.P7.slice(2));
  assert.equal(r.afterRegisters[1],r.before.P8.slice(2));
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(e=>e.ip!==0xC9));
  for(const [i,carrier,slot,value] of [[1,13,'V',r.before.P8.slice(2)],[2,13,'V',r.before.P8.slice(2)],
    [3,14,'W','0000F0000000']]) {
    const stage='upper-after-'+i;routes.push(checkPairedPath(es,stage,carrier,slot));
    const at=es.findIndex(e=>e.stage===stage&&e.ip===0xE7&&e.nextIp===0xA8);
    const block=checkSwapBlock(r,at,4);
    assert.equal(raw(block.body[0].r,0),value);assert.equal(raw(block.after.ring.X),value);
  }
  const first=es.find(e=>e.stage==='upper-after-1');
  for(const word of Object.keys(r.before))assert.equal(raw(first.ring[word],1,14),r.after[word]);
  assert.ok(r.traced.writes.filter(w=>w.command>=first.command&&Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value),'both readers and marker reload leave every Ms tetra unchanged');
  console.log('PASS: phase',phaseOffset,JSON.stringify(routes),'repeated P1 recall and P2 marker recall; full native ROM paths and stack writes.');
}
console.log('LIMIT: this loader-only test deliberately ends with a visible and hidden marker; it is not the complete cleanup protocol.');
