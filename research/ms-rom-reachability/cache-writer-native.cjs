#!/usr/bin/env node
'use strict';
// Selected native continuation only. Fixed keys/frames; passive observation.
// No ROM edits, no R/ST/IP/M writes, no observer-controlled action timing.
const assert=require('node:assert/strict');
const {reader,plainReader}=require('./check_partial_k2_cache_exit.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const positions=[0,3,9,12,18,21],keys=['F','Сx',','];
const hex=a=>a.map(n=>n.toString(16).toUpperCase()).join('');
const lane=(a,n)=>Array.from({length:12},(_,i)=>a[3*i+n]);

function capture({mirror=true}={}) {
  const calc=reader(fixtures[1]);
  const payload=positions.map(i=>calc.ik1302.r[i]);
  const result=trace(calc,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
    ringAt:e=>[0x8C,0xDC,0xDE,0xD4,0xE7,0xAF].includes(e.ip),
  });
  const dc=result.events.find(e=>e.ip===0xDC);
  assert.ok(dc,'selected continuation reaches DC');
  const before=result.events.filter(e=>e.command<=dc.command);
  assert.ok(!before.some(e=>e.ip===0xEE));
  // Cache transport moves the six raw tetras between lanes; do not confuse
  // preservation of their identities with remaining in the initial A slots.
  if(mirror) {
    const plain=plainReader(fixtures[1]);plain.pressSequence(keys);aligned(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc));
  }
  return {...result,keys,payload};
}
function summary(r) {
  const sequence=[];
  for(const e of r.events) if(sequence.at(-1)!==e.ip)sequence.push(e.ip);
  return {scope:'one selected native continuation; no hypothesized state changes',keys,
    route:sequence.map(n=>n.toString(16).toUpperCase()).join(' '),
    states:r.events.filter(e=>[0x8C,0xDC,0xEA,0xDE,0xD4,0xE7,0xAF].includes(e.ip))
      .map(e=>({ip:e.ip.toString(16).toUpperCase(),command:e.command,slot:e.slot,
        A:hex(lane(e.r,0)),B:hex(lane(e.r,1)),C:hex(lane(e.r,2)),
        r34:e.r[34],st34:e.st[34],s1:e.s1,sp:e.sp,next:e.nextIp}))};
}
if(require.main===module) {
  const r=capture({mirror:!process.argv.includes('--proof-input')});
  console.log(JSON.stringify(process.argv.includes('--proof-input')?r:summary(r)));
}
module.exports={capture,summary,keys,positions};
