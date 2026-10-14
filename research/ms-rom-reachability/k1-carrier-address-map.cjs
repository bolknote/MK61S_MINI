#!/usr/bin/env node
'use strict';
// CONDITIONAL offline execution from one native observer snapshot. Vary the
// operand nibble to understand the ROM address scan, never a live calculator.
const assert=require('node:assert/strict');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
function simulate(entry,index,{pointer}={}) {
  assert.equal(entry.ip,0xA5);assert.ok(entry.ring);
  const chip=new MK61().ik1302;
  chip.reset();chip.r=entry.r.slice();chip.stack=entry.st.slice();
  for(const field of ['s','s1','l','t','carry','keyX','keyY'])chip[field]=entry[field];
  chip.r[32]=index;
  const ring=structuredClone(entry.ring);
  if(pointer)[...pointer].reverse().forEach((n,i)=>{ring.U[i*3]=parseInt(n,16);});
  let slot=slots.indexOf(entry.slot);chip.memory=ring[entry.slot].slice();
  const path=[],writes=[];
  for(let step=0;step<240;step++) {
    const ip=chip.r[36]+16*chip.r[39],name=slots[slot];
    path.push({ip,slot:name,a:raw(chip.r,0),r29:chip.r[29],r32:chip.r[32],r35:chip.r[35],s1:chip.s1,
      m1:raw(ring[name],0),sp:[0,1,2].map(i=>chip.stack[36+i]+16*chip.stack[39+i])});
    if(step&&ip===0xA5)break;
    const out=[];
    for(let j=0;j<42;j++){chip.input=ring[slots[(slot+1)%15]][j];chip.tick();out.push(chip.output);}
    for(let j=0;j<42;j++)if(out[j]!==ring[name][j])writes.push({step,ip,slot:name,nibble:j,before:ring[name][j],value:out[j]});
    ring[name]=out;slot=(slot+1)%15;
  }
  return {index,pointerOverride:pointer??null,path,writes,
    d6:path.filter(e=>e.ip===0xD6),d4:path.filter(e=>e.ip===0xD4),ee:path.filter(e=>e.ip===0xEE),
    finalP0:raw(ring.U,0),limit:'conditional offline operand study, not a keyboard path'};
}
function entryFromTrace(r) {
  const e=r.traced.events.find(e=>e.stage==='indirect-p'&&e.ip===0xA5);assert.ok(e&&e.ring);return e;
}
module.exports={simulate,entryFromTrace};
