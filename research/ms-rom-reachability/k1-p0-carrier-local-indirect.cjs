#!/usr/bin/env node
'use strict';
// CONDITIONAL local IK1302 execution, NOT a reachable keyboard entry.
// Investigate indirect A through physical P0=m under Z/T markers.
const {MK61}=require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const raw=(a,lane=1)=>Array.from({length:12},(_,j)=>a[lane+3*j].toString(16)).reverse().join('').toUpperCase();
function run({index=10,start='U',pointer='0000F0000000',pointerSlot='U'}={}) {
  const chip=new MK61().ik1302;chip.reset();
  const pages=Object.fromEntries(slots.map(n=>[n,Array(42).fill(0)]));
  for(const n of ['marker','Z','T'])pages[n][22]=15;
  const set=(n,lane,s)=>[...s].reverse().forEach((v,j)=>pages[n][lane+3*j]=parseInt(v,16));
  set(pointerSlot,0,pointer);set('X',1,'002010100000');set('Y',1,'002033300000');
  chip.r[36]=6;chip.r[39]=13;chip.r[29]=index+1;chip.r[32]=index;
  chip.r[35]=1;chip.r[26]=15;chip.s1=6;
  [0x2F,0xAC,0x9A].forEach((v,i)=>{chip.stack[36+i]=v%16;chip.stack[39+i]=v>>4;});
  let slot=slots.indexOf(start);const path=[],writes=[];
  chip.memory=pages[start].slice();
  for(let step=0;step<180;step++) {
    const n=slots[slot],ip=chip.r[36]+16*chip.r[39];
    path.push([ip.toString(16),n,raw(chip.r,0),chip.s1]);
    if(step&&ip===0xA5)break;
    const after=[];for(let j=0;j<42;j++){chip.input=pages[slots[(slot+1)%15]][j];chip.tick();after.push(chip.output);}
    for(let j=0;j<42;j++)if(after[j]!==pages[n][j])writes.push([step,ip.toString(16),n,j,pages[n][j],after[j]]);
    pages[n]=after;slot=(slot+1)%15;
  }
  return {premises:{index,start,pointer,pointerSlot,markers:['marker','Z','T']},path,writes,finalP0:raw(pages.U,0)};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2]?JSON.parse(process.argv[2]):{}),null,2));
module.exports={run};
