'use strict';
// DETACHED literal ALL5 interpreter. Plain numeric arrays, no MK61/chip
// instance and no native state import. Original ROM and exact ring order.
const assert=require('node:assert/strict');
const {step:wordStep}=require('./cache-bc-head93-primary-word-model.cjs');
const rom=require('/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs');
const names=['ir2a','ir2b','ik1302','ik1303','ik1306'];
const roman={ik1302:rom.ИК1302,ik1303:rom.ИК1303,ik1306:rom.ИК1306};
function make(entry){
  const chips=structuredClone(entry.fullBefore),tags=structuredClone(entry.tagsBefore);
  assert.equal(chips.ir2a.tick,chips.ir2b.tick);
  for(const chip of names.slice(2))assert.equal(chips[chip].tick,0);
  return{chips,tags,phase:chips.ir2a.tick};
}
function step(core,pins) {
  const {chips,tags,phase}=core,oldA=chips.ir2a.m.slice(phase,phase+42);
  const incoming=chips.ir2b.m.slice(phase,phase+42),emitted={};
  for(const chip of names.slice(2)) {
    const [keyX,keyY]=pins[chip],source=chip==='ik1302'?incoming:emitted[chip==='ik1303'?'ik1302':'ik1303'];
    const result=wordStep(chips[chip],keyX,keyY,source,roman[chip]);
    chips[chip]={...result.state,keyX,keyY,tick:0};emitted[chip]=result.out;
  }
  chips.ir2a.m.splice(phase,42,...emitted.ik1306);
  chips.ir2b.m.splice(phase,42,...oldA);
  const wire={ik1302:[incoming[40],emitted.ik1302[41]],ik1303:[emitted.ik1302[41],emitted.ik1303[41]],
    ik1306:[emitted.ik1303[41],emitted.ik1306[41]],ir2a:[emitted.ik1306[41],oldA[41]],ir2b:[oldA[41],incoming[41]]};
  core.phase=(phase+42)%252;
  for(const chip of names) {
    [chips[chip].input,chips[chip].output]=wire[chip];
    if(chip.startsWith('ir'))chips[chip].tick=core.phase;
  }
  for(let j=0;j<42;j++) {
    const at=phase+j,old=names.map(n=>tags[n][n.startsWith('ir')?at:j]);
    for(let k=0;k<5;k++)tags[names[k]][k<2?at:j]=old[(k+4)%5];
  }
  return emitted;
}
function compare(core,target,targetTags) {
  assert.equal(core.phase,target.ir2a.tick);
  for(const chip of names) {
    const current=core.chips[chip];
    for(const field of ['m','tick','input','output',...(chip.startsWith('ir')?[]:['r','st','s','s1','l','t','carry'])])
      assert.deepEqual(current[field],target[chip][field],chip+'/'+field);
    assert.deepEqual(core.tags[chip],targetTags[chip],chip+'/all passive carrier identities');
  }
}
function pins(v){return Object.fromEntries(names.slice(2).map(n=>[n,[v.fullBefore[n].keyX,v.fullBefore[n].keyY]]));}
function physical(core,cells,area,word){
  const out=Array(12);
  for(const chip of names)core.tags[chip].forEach((tag,j)=>{
    const cell=cells[tag];
    if(cell.area===area&&cell.word===word&&Number.isInteger(cell.field))out[cell.field]=core.chips[chip].m[j];
  });
  // Array#every skips holes. Require all twelve physical fields, so a wrong
  // area/word query cannot silently masquerade as an empty numerical word.
  assert.ok(Array.from(out).every(Number.isInteger),'missing physical field: '+area+':'+word);
  return out.reverse().map(n=>n.toString(16).toUpperCase()).join('');
}
module.exports={make,step,compare,pins,physical,names};
