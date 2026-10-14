#!/usr/bin/env node
'use strict';
// Exploratory probe, not a physical keyboard protocol; see the research README.
const { MK61 } = require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
const hex = x => x.toString(16).toUpperCase().padStart(2, '0');
const relevant = new Set([0x1F,0x1D,0x25,0x26,0x28,0x36,0x7E,0x77,0x6D,0x60,0xC7,0xC8,0xDD,0xD4]);
function probe(code, value='3', registerValue='7') {
  const c=new MK61();
  c.loadProgram([code,0x50]);
  for(let i=0;i<15;i++) c.setRegister(i.toString(16),registerValue);
  c.inputNumber(value,{clear:true});
  c.press('В/О');
  const chip=c.ik1302, tick=chip.tick, events=[];
  let prev=null;
  chip.tick=function(){
    if(this.tickIndex===0){
      const ip=this.r[36]+16*this.r[39];
      if(relevant.has(ip)) events.push({ip,prev,s1:this.s1,
        r:[0,25,26,28,31,34,35,38].map(i=>this.r[i])});
      prev=ip;
    }
    return tick.call(this);
  };
  c.press('С/П');
  c.runUntilStable({maxFrames:12,stableFrames:4});
  chip.tick=tick;
  return {code:hex(code), value,registerValue,pc:c.programCounter(),display:c.displayText(),
    events:events.slice(0,48).map(e=>`${hex(e.prev)}>${hex(e.ip)} s${hex(e.s1)} `
      +`r${e.r.map(x=>x.toString(16).toUpperCase()).join('')}`)};
}
for(const code of [0x47,0x67,0x77,0x87,0x97,0xA7,0xB7,0xC7,0xD7,0xE7,0xF7])
  console.log(JSON.stringify(probe(code)));
