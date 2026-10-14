#!/usr/bin/env node
'use strict';
// A3 observations only: the heuristic E2 call/return grouping below is NOT reliable.
const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const { makeProgram } = require('/Users/bolk/Projects/MK-61/tests/emulator/probe-pustyshka-program.cjs');
const hex = x => x.toString(16).toUpperCase().padStart(2,'0');
function run(label, action){
 const calc=new MK61(), chip=calc.ik1302, tick=chip.tick, histories=[];
 let buffer=[],lastVector=null,lastWriter=null,previousIp=null;
 const roots=[];
 chip.tick=function(){
  if(this.tickIndex===0){
   const ip=this.r[36]+16*this.r[39], vector=this.r[37]+16*this.r[40];
   if(lastVector!==null&&vector!==lastVector)lastWriter=previousIp;
   const sp=[0,1,2].map(i=>this.stack[36+i]+16*this.stack[39+i]);
   if(ip===0xE2) roots.push({sp:sp[0],ips:[],vectors:[],done:false});
   for(const root of roots)if(!root.done){
    root.ips.push(ip);root.vectors.push(vector);
    if(root.ips.length>1&&ip===root.sp)root.done=true;
    if(root.ips.length>1500)root.done=true;
   }
   buffer.push(`${hex(ip)}[${hex(vector)}:${sp.map(hex).join('/')}]`);
   if(buffer.length>12)buffer.shift();
   if(ip===0xA3)histories.push({vector:hex(vector),lastWriter:hex(lastWriter),tail:buffer.join(' ')});
   lastVector=vector;previousIp=ip;
  }
  return tick.call(this);
 };
 action(calc);chip.tick=tick;
 const byRoute=new Map();
 for(const root of roots){
  const chain=root.ips.filter((ip,i)=>ip!==root.ips[i-1]);
  const key=chain.map(hex).join(' ');
  byRoute.set(key,{sp:hex(root.sp),lastVector:hex(root.vectors.at(-1)),length:root.ips.length,route:key});
 }
 const a3Counts={};
 for(const h of histories){const k=`${h.vector} via ${h.lastWriter}`;a3Counts[k]=(a3Counts[k]||0)+1;}
 console.log(JSON.stringify({label,a3Counts,examples:histories.slice(0,3),routes:[...byRoute.values()].slice(0,12)}));
}
run('numeric',c=>{c.inputNumber('12345678',{clear:true});c.press('X→П').press('7');c.press('K').press('П→X').press('7');c.runFrames(4);});
run('false marker',c=>{const {program}=makeProgram({literal:true,repeats:1});c.loadProgram(program);c.press('В/О').press('С/П');c.runUntilStable({maxFrames:2000,stableFrames:8});});
