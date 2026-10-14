#!/usr/bin/env node
'use strict';
// Fixed architectural continuations only; no state-controlled key timing.
const assert=require('node:assert/strict');
const {reader,plainReader}=require('./check_partial_k2_cache_exit.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const lane=(a,n)=>Array.from({length:12},(_,i)=>a[3*i+n]);
const hex=a=>a.map(n=>n.toString(16).toUpperCase()).join('');
const protocols=[
  ['F','Сx','БП','4','0'],
  ['F','Сx','В/О'],
  ['F','Сx','В↑'],
  ['F','Сx','F','ВП'],
  ['F','Сx','К','ВП'],
  ['F','Сx','БП','4','0',','],
  ['F','Сx','↔'],
  ['F','Сx','F','В↑'],
];
function capture(keys) {
  const calc=reader();
  const result=trace(calc,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
  });
  const ee=result.events.findIndex(e=>e.ip===0xEE);
  const before=ee<0?result.events:result.events.slice(0,ee+1);
  const sequence=[];
  for(const e of before) if(sequence.at(-1)!==e.ip)sequence.push(e.ip);
  const ips=new Set([0xBE,0xAC,0x8C,0x40,0x47,0x93,0x94,0x95,0x4E,0x74,0xEC]);
  const plain=plainReader(fixtures[1]);
  plain.pressSequence(keys);aligned(plain);
  assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc),
    'complete fresh native mirror, fixed keys and waits, without observers');
  const final=machineSnapshot(calc).ik1302;
  return {keys,read:ee>=0,
    completeFreshMirror:true,
    route:sequence.map(n=>n.toString(16).toUpperCase()).join(' '),
    tail:before.filter(e=>ips.has(e.ip)).map(e=>({
      ip:e.ip.toString(16).toUpperCase(),r33:e.r[33],st:e.st.slice(27,36),
      A:hex(lane(e.r,0)),B:hex(lane(e.r,1)),C:hex(lane(e.r,2)),
    })),final:{r2:final.r[2],r5:final.r[5],r23:final.r[23],r33:final.r[33],
      stTail:final.st.slice(27,36),A:hex(lane(final.r,0)),
      B:hex(lane(final.r,1)),C:hex(lane(final.r,2))}};
}
if(require.main===module) for(const keys of protocols)console.log(JSON.stringify(capture(keys)));
module.exports={capture,protocols};
