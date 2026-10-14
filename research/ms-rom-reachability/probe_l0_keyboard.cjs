#!/usr/bin/env node
'use strict';
// Program and numeric setup both use the calculator keyboard.
// No modification of internal registers or microcode.
const assert = require('node:assert/strict');
const path = require('node:path');
const { MK61 } = require(path.join(process.env.MK61_REFERENCE_ROOT ||
  path.resolve(__dirname, '../../..', 'MK-61'), 'tests/emulator/mk61.cjs'));
const hex = n => n.toString(16).toUpperCase().padStart(2,'0');
function run(counter, x='12345673', mode='run') {
  const calc=new MK61();
  calc.pressSequence(['F','ВП','F','П→X','0','3','С/П','С/П','F','/-/','В/О']);
  assert.deepEqual([0,1,2,3].map(i=>calc.readCommand(i)),[0x5D,0x03,0x50,0x50]);
  calc.inputNumber(counter,{clear:true}).pressSequence(['X→П','0']);
  calc.inputNumber(x,{clear:true}).press('В/О');
  const chip=calc.ik1302, tick=chip.tick, events=[], primitives=[];
  const observed=new Set();
  let snapshot=null, active=false;
  chip.tick=function(){
    if(this.tickIndex===0){
      const ip=this.r[36]+16*this.r[39];
      observed.add(ip);
      if(ip===0xC7 || ip===0xC8)primitives.push(ip);
      if(!snapshot && ip===0xAB && this.r[35]===5 && this.r[32]===13){
        snapshot={r:this.r.slice(),m:this.memory.slice(),st:this.stack.slice(),
          s:this.s,s1:this.s1,l:this.l,t:this.t,carry:this.carry};
        active=true;
      }
      if(active && events.length<260)events.push({ip,r0:this.r[0],r2:this.r[2],r4:this.r[4],
        r21:this.r[21],r25:this.r[25],r26:this.r[26],r27:this.r[27],r31:this.r[31],r32:this.r[32],
        r34:this.r[34],r35:this.r[35],r38:this.r[38],s1:this.s1,
        vector:this.r[37]+16*this.r[40],
        sp:[0,1,2].map(i=>this.stack[36+i]+16*this.stack[39+i])});
    }
    return tick.call(this);
  };
  try {
    if(mode==='manual')calc.pressSequence(['F','П→X']);
    else calc.press(mode==='step' ? 'ШГ→' : 'С/П');
    calc.runUntilStable({maxFrames:12,stableFrames:4});
  }
  finally {chip.tick=tick;}
  return {counter,x,mode,pc:calc.programCounter(),display:calc.displayText(),snapshot,events,
    observed:[...observed],primitives};
}
module.exports={run};
if(require.main===module)for(const value of process.argv.includes('--one') ? ['1'] : ['0','1','2']) {
  const mode=process.argv.includes('--manual') ? 'manual' :
    process.argv.includes('--step') ? 'step' : 'run';
  const report=run(value,'12345673',mode);
  if(process.argv.includes('--json'))console.log(JSON.stringify(report));
  else console.log(JSON.stringify({counter:value,mode,snapshot:report.snapshot,
    events:report.events.filter(e=>[0xDD,0xD6,0xD4,0x37,0x38,0x07,0x6D,0x6F,0x62,0x6E,0x60,0xC8].includes(e.ip))
      .map(e=>({...e,ip:hex(e.ip)})),pc:report.pc,display:report.display}));
}
