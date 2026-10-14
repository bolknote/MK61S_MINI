#!/usr/bin/env node
'use strict';
// Five architecture-derived controls, not a keyboard sweep: the three public
// frame phases of the saved0/2/D state, and two standard stack operations.
// A normal ROLL would separate Y/Z (oldT is different); SWAP starts from
// equal RAW X/Y. Actual ghost formatting may still write or destroy them.
// Public keys only, observer-owned carrier tags, fresh unobserved ALL5 mirror.
const assert=require('node:assert/strict');
const {setup,aligned,rawRegister,dump,sample,hashes}=
  require('./cache-bc-head93-indirect-ghost-native.cjs');
const {initialTags}=require('./cache-bc-head93-native-carriers.cjs');
const chips=[null,'ir2a','ir2b','ik1302','ik1303','ik1306'];
const visible={X:[5,34],Y:[4,34],Z:[3,34],T:[2,118],X1:[2,160]};
const extra={U:[2,202],V:[2,244],W:[2,34],Q:[2,76],
  P7:[1,118],P8:[1,160],P9:[1,202],P10:[1,244]};
const raw=a=>a.slice(0,12).reverse().map(v=>v.toString(16).toUpperCase()).join('');
function data(c) {
  assert.equal(c.ir2a.tickIndex,84);
  return {program:Array.from({length:105},(_,i)=>c.readCommand(i)),
    registers:Array.from({length:15},(_,i)=>rawRegister(c,i)),
    stack:Object.fromEntries(Object.entries(visible).map(([n,[chip,end]])=>
      [n,raw(Array.from({length:12},(_,i)=>c.memoryForChip(chip)[end-33+3*i]))])),
    ms:Object.fromEntries(Object.entries(extra).map(([n,[chip,end]])=>
      [n,Array.from({length:14},(_,i)=>c.memoryForChip(chip)[end-33+3*i])]))};
}
function changed(a,b) {
  return Object.fromEntries(Object.entries(a).map(([area,rows])=>[area,
    Object.keys(rows).filter(n=>JSON.stringify(rows[n])!==JSON.stringify(b[area][n]))
      .map(n=>({word:n,before:rows[n],after:b[area][n]}))]));
}
function run(spec,{log=true}={}) {
  hashes();const c=setup(true,'10',3,false,true),plain=setup(true,'10',3,false,true);
  assert.deepEqual(dump(c),dump(plain));
  for(const x of [c,plain]) {x.pressSequence(['П→X','9']).runFrames(8);aligned(x);}
  assert.deepEqual(dump(c),dump(plain));assert.deepEqual(sample(c).ST2,[0,2,13]);
  const seed=data(c),{tags,cells}=initialTags(c),original=c.tick.bind(c);
  const events=[],writers=[];let words=-1,reading=false,event=null,bb=0,bc=0;
  c.tick=function() {
    const indices=chips.map((n,i)=>i?this[n].tickIndex:0);
    if(indices[3]===0) {
      words++;const s=sample(this);
      if(reading&&s.ip===0xBB)bb++;
      if(reading&&s.ip===0xBC)bc++;
      event=reading&&[0xEE,0xE3,0xE4,0xA3,0xBB,0xBC,0xE7].includes(s.ip)
        ? {word:words,...s,ir2aTick:indices[1],
          owners:[...new Set(tags[3].filter((_,j)=>j%3===1).map(id=>
            cells[id].area+':'+cells[id].word))],
          before:this.ik1302.memory.slice(),B:this.ik1302.r.filter((_,j)=>j%3===1),emitted:[]}
        : null;
      if(event)events.push(event);
    }
    const old=indices.map((j,i)=>i?tags[i][j]:0),result=original();
    const incoming=[0,old[5],old[1],old[2],old[3],old[4]];
    const output=[0,this.ir2a.output,this.ir2b.output,this.ik1302.output,
      this.ik1303.output,this.ik1306.output];
    const input=[0,output[5],output[1],output[2],output[3],output[4]];
    for(let i=1;i<=5;i++) {
      assert.equal(this[chips[i]].memory[indices[i]],input[i]);
      tags[i][indices[i]]=incoming[i];
    }
    if(event) {
      event.emitted.push(this.ik1302.output);
      if(this.ik1302.tickIndex===0) {
        event.after=sample(this);
        event.numericChanged=event.emitted.flatMap((v,j)=>j%3===1&&j<36&&v!==event.before[j]
          ? [j] : []);
        if(event.ip===0xBC)writers.push(event);
      }
    }
    return result;
  };
  if(spec.between) for(const x of [c,plain]) {
    x.pressSequence(spec.between).runFrames(8);aligned(x);
  }
  assert.deepEqual(dump(c),dump(plain));
  const afterOperation=data(c),operationState=sample(c);
  for(const x of [c,plain])x.runFrames(spec.idle);
  assert.deepEqual(dump(c),dump(plain));
  const readState={...sample(c),ir2aTick:c.ir2a.tickIndex};reading=true;
  for(const x of [c,plain]) {x.pressSequence(['П→X','9']).runFrames(8);aligned(x);}
  assert.deepEqual(dump(c),dump(plain),'whole suffix fresh unobserved ALL5 mirror');
  const end=data(c);
  if(!spec.between) {
    assert.equal(bb,1);assert.equal(bc,1);
    assert.deepEqual(operationState.ST2,[0,2,13]);
    assert.equal(writers.length,1);assert.deepEqual(writers[0].owners,['stack:Z']);
    assert.deepEqual(writers[0].numericChanged,[]);
    for(const area of ['program','registers','ms'])assert.deepEqual(changed(seed,end)[area],[]);
  } else {
    assert.equal(bb,0);assert.equal(bc,0);
    assert.deepEqual(operationState.ST2,[0,0,9]);
    assert.deepEqual(operationState.ST1,[0,0,0]);
    assert.equal(c.displayText(),'ЕГГ0Г');
    assert.equal(afterOperation.stack.Y,'000000000000');
    for(const area of ['program','registers','ms'])assert.deepEqual(changed(seed,end)[area],[]);
  }
  const report={case:spec.name,idleFrames:spec.idle,between:spec.between||[],
    operationState,readState,bb,bc,display:c.displayText(),ALL5mirror:true,
    operationChanges:changed(seed,afterOperation),readChanges:changed(afterOperation,end),
    writers:writers.map(e=>({word:e.word,owners:e.owners,
      before:raw(e.before.filter((_,j)=>j%3===1)),
      after:raw(e.emitted.filter((_,j)=>j%3===1)),numericChanged:e.numericChanged})),
    chosen:events.filter(e=>e.ip===0xE3&&e.tags[0]===0xAD||e.ip===0xA3&&e.vector===0xCC)
      .map(e=>({word:e.word,ip:e.ip,C:e.C,ST1:e.ST1,ST2:e.ST2,
        tags:e.tags,owners:e.owners,ir2aTick:e.ir2aTick})),
    onlyPublicKeys:true,carrierTagsNeverLoaded:true,fullK2:false};
  hashes();if(log)console.log(JSON.stringify(report));return report;
}
const specs=[{name:'idle_phase1',idle:0},{name:'idle_phase2',idle:1},
  {name:'idle_phase0',idle:2},{name:'one_roll',idle:0,between:['F',',']},
  {name:'equal_raw_xy_swap',idle:0,between:['↔']}];
if(require.main===module) {
  for(const spec of specs)run(spec);
  console.log('PASS five source-selected phase/separation controls, fresh ALL5 mirrors; '
    +'no setter/state/ROM/IP repair, native payload-family theorem, live test or fullK2.');
}
module.exports={run,specs};
