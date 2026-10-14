#!/usr/bin/env node
'use strict';
// Passive carrier identities, NOT value provenance. Tags live only in this
// observer and are never assigned to calculator memory. Derive the five-cell
// routing from the original MK61.tick/IK13.tick/IR2.tick/closeRing equations;
// assert their actual native cell values on EVERY tick, and mirror all chips
// against a fresh unobserved public-key execution at phase-aligned endpoints.
const assert = require('node:assert/strict');
const {setup,aligned,rawRegister,dump,sample,hashes} =
  require('./cache-bc-head93-indirect-ghost-native.cjs');
const chips = [null,'ir2a','ir2b','ik1302','ik1303','ik1306'];
const sizes = [0,252,252,42,42,42];
const visible = {X:[5,34],Y:[4,34],Z:[3,34],T:[2,118],X1:[2,160]};
const extra = {U:[2,202],V:[2,244],W:[2,34],Q:[2,76],
  P7:[1,118],P8:[1,160],P9:[1,202],P10:[1,244]};
const primary=c=>{const p=c.ik1302;return {r:p.r.slice(),st:p.stack.slice(),
  m:p.memory.slice(),s:p.s,s1:p.s1,l:p.l,t:p.t,carry:p.carry};};
const fullState=c=>Object.fromEntries(chips.slice(1).map(name=>{
  const p=c[name];
  return [name,{m:p.memory.slice(),tick:p.tickIndex,input:p.input,output:p.output,
    ...(name.startsWith('ik')?{r:p.r.slice(),st:p.stack.slice(),s:p.s,s1:p.s1,
      l:p.l,t:p.t,carry:p.carry,keyX:p.keyX,keyY:p.keyY}:{})}];
}));
const fullTags=tags=>Object.fromEntries(chips.slice(1).map((name,i)=>[name,tags[i+1].slice()]));
const working=(c,offset)=>c.ik1302.r.filter((_,j)=>j%3===offset).slice(0,12);
const raw=a=>a.slice(0,12).reverse().map(v=>v.toString(16).toUpperCase()).join('');

function initialTags(c) {
  assert.equal(c.ir2a.tickIndex,84);
  let next=0;
  const tags=sizes.map(n=>Array.from({length:n},()=>next++));
  assert.equal(next,630);
  const cells=Array.from({length:630},()=>null);
  function assign(chip,index,area,word,field) {
    const tag=tags[chip][index];
    assert.equal(cells[tag],null,'physical cells must not alias');
    cells[tag]={chip,index,area,word,field};
  }
  function numeric(chip,end,area,word) {
    for(let digit=0;digit<12;digit++) assign(chip,end-33+3*digit,area,word,digit);
    assign(chip,end+3,area,word,'service0');
    assign(chip,end+6,area,word,'service1');
  }
  for(let i=0;i<15;i++) {
    const [chip,end]=c.commandAddress(i*7,1);
    numeric(chip,end-8,'register','R'+i.toString(16).toUpperCase());
  }
  for(let i=0;i<105;i++) {
    const [chip,end]=c.commandAddress(i,1);
    assign(chip,end-3,'program',i,'lo');assign(chip,end,'program',i,'hi');
  }
  for(const [word,[chip,end]] of Object.entries(visible)) numeric(chip,end,'stack',word);
  for(const [word,[chip,end]] of Object.entries(extra)) numeric(chip,end,'Ms',word);
  // Two remaining numeric-lane words: no unproved functional names.
  numeric(1,34,'unclassified','aux0');numeric(1,76,'unclassified','aux1');
  assert.ok(cells.every(Boolean));
  return {tags,cells};
}

function lane(c,cells,tags,offset) {
  const ids=tags[3].filter((_,j)=>j%3===offset), owners=ids.map(id=>cells[id]);
  const values=c.ik1302.memory.filter((_,j)=>j%3===offset);
  return {cells:owners,values};
}

function run({log=true,all5=false,modeRepair=false}={}) {
  hashes();const c=setup(true,'10',3,false,true),plain=setup(true,'10',3,false,true);
  assert.deepEqual(dump(c),dump(plain));
  const fullPrepared=all5?fullState(c):undefined;
  for(const x of [c,plain]) {x.pressSequence(['П→X','9']).runFrames(8);aligned(x);}
  assert.deepEqual(dump(c),dump(plain));assert.deepEqual(sample(c).ST2,[0,2,13]);
  const fullSeeded=all5?fullState(c):undefined;
  const {tags,cells}=initialTags(c),originalTags=tags.map(a=>a.slice());
  const original=c.tick.bind(c),events=[],records=[],carrierCycle=[],landmarks={};
  let ticks=0,word=-1,event=null,bb=0,bc=0,active=false,done=false,record=null;
  c.tick=function() {
    const indices=chips.map((name,i)=>i?this[name].tickIndex:0);
    if(indices[3]===0) {
      word++;const s=sample(this);
      if(all5&&[1154,1200,1212].includes(word)) {
        landmarks[word]={word,ip:s.ip,fullBefore:fullState(this),tagsBefore:fullTags(tags),
          keysX:Array(42).fill(this.ik1302.keyX),
          keysY:Array(42).fill(this.ik1302.keyY)};
      }
      const owners=[...new Set(tags[3].filter((_,j)=>j%3===1).map(id=>
        cells[id].area+':'+cells[id].word))];
      assert.equal(owners.length,1);
      if(word<15)carrierCycle.push(owners[0]);
      else assert.equal(owners[0],carrierCycle[word%15]);
      if(s.ip===0xBB)bb++;if(s.ip===0xBC)bc++;
      if(!active&&!done&&s.ip===0xEE&&s.tags[0]===0xE3) active=true;
      if(active) {record={word,ip:s.ip,ir2aTick:indices[1],numericOwner:owners[0],before:primary(this),
        keysX:[],keysY:[],serial:[],emitted:[]};
        if(all5) {record.fullBefore=fullState(this);record.tagsBefore=fullTags(tags);}
        records.push(record);}
      event=[0xE3,0xE4,0xEE,0xA3,0xBB,0xBC,0xE7,0xBE].includes(s.ip)
        ? {word,...s,ir2aTick:indices[1],
          A:working(this,0),B:working(this,1),
          numeric:lane(this,cells,tags,1),emitted:[]} : null;
      if(event) events.push(event);
    }
    const old=indices.map((j,i)=>i?tags[i][j]:0);
    const observe=active;
    if(observe) {record.keysX.push(this.ik1302.keyX);record.keysY.push(this.ik1302.keyY);}
    const result=original();
    // All writes below are to observer-owned tags, never to the emulator.
    const incoming=[0,old[5],old[1],old[2],old[3],old[4]];
    const output=[0,this.ir2a.output,this.ir2b.output,
      this.ik1302.output,this.ik1303.output,this.ik1306.output];
    const input=[0,output[5],output[1],output[2],output[3],output[4]];
    for(let i=1;i<=5;i++) {
      assert.equal(this[chips[i]].memory[indices[i]],input[i],
        'native five-cell routing/closeRing at tick'+ticks+' chip'+i);
      tags[i][indices[i]]=incoming[i];
    }
    if(event) {
      event.emitted.push(this.ik1302.output);
      if(this.ik1302.tickIndex===0) {
        event.after=sample(this);
        event.afterA=working(this,0);event.afterB=working(this,1);
        event.changed=event.emitted.flatMap((v,j)=>j%3===1&&v!==event.numeric.values[(j-1)/3]
          ? [{position:j,cell:event.numeric.cells[(j-1)/3],
            before:event.numeric.values[(j-1)/3],after:v}] : []);
      }
    }
    if(observe) {
      record.serial.push(this.ir2b.output);record.emitted.push(this.ik1302.output);
      if(this.ik1302.tickIndex===0) {
        record.after=primary(this);
        if(all5) {record.fullAfter=fullState(this);record.tagsAfter=fullTags(tags);}
        if(record.ip===0xBE) {active=false;done=true;}
      }
    }
    ticks++;return result;
  };
  for(const x of [c,plain]) {x.pressSequence(['П→X','9']).runFrames(8);aligned(x);}
  assert.deepEqual(dump(c),dump(plain),'full suffix fresh unobserved ALL5 mirror');
  if(modeRepair) {
    for(const x of [c,plain]) {
      x.pressSequence(['F','/-/']);aligned(x);
      x.pressSequence(['П→X','9']).runFrames(8);aligned(x);
    }
    assert.deepEqual(dump(c),dump(plain),'fresh unobserved AUTO/third-read ALL5 mirror');
  }
  assert.equal(ticks,(modeRepair?16800:6720)*42);
  if(modeRepair) {assert.ok(bb>=1&&bc>=1);} else {assert.equal(bb,1);assert.equal(bc,1);}
  assert.ok(done);assert.equal(records.length,122);
  assert.equal(records[0].word,1214);assert.equal(records[0].ip,0xEE);
  assert.equal(records.at(-1).ip,0xBE);
  assert.ok(records.every((e,i)=>e.serial.length===42&&e.emitted.length===42
    &&(!i||e.word===records[i-1].word+1)));
  assert.deepEqual(tags,originalTags,'complete native suffix restores carrier permutation');
  assert.equal(carrierCycle.length,15);assert.equal(new Set(carrierCycle).size,15);
  const bcEvent=events.find(e=>e.ip===0xBC);
  assert.ok(bcEvent.numeric.cells.every(x=>x.area==='stack'&&x.word==='Z'));
  const zeroEvent=events.find(e=>e.ip===0xE7&&e.word>bcEvent.word);
  assert.ok(zeroEvent.numeric.cells.every(x=>x.area==='stack'&&x.word==='Y'));
  const sourceEE=events.find(e=>e.word===records[0].word);
  assert.ok(sourceEE.numeric.cells.every(x=>x.area==='stack'&&x.word==='Y'));
  const actualE4=events.find(e=>e.word===1228);
  assert.deepEqual(actualE4.A,sourceEE.numeric.values.slice(0,12));
  assert.deepEqual(actualE4.afterB,actualE4.A);
  const bbEvent=events.find(e=>e.ip===0xBB);
  assert.deepEqual(bbEvent.B,actualE4.A);
  assert.deepEqual(bcEvent.emitted.filter((_,j)=>j%3===1).slice(0,12),actualE4.A);
  const compact=e=>({word:e.word,ip:e.ip.toString(16).toUpperCase(),
    ir2aTick:e.ir2aTick,C:e.C,ST1:e.ST1,ST2:e.ST2,tags:e.tags,
    owners:[...new Set(e.numeric.cells.map(x=>x.area+':'+x.word))],
    raw12:raw(e.numeric.values),out12:raw(e.emitted.filter((_,j)=>j%3===1)),
    A:raw(e.A),B:raw(e.B),afterB:raw(e.afterB),changed:e.changed});
  const report={ticks,macroWords:word+1,primaryWindow:records.length,all5Snapshots:all5,modeRepair,bb,bc,carrierCycle,
    selected:events.filter(e=>e.word<=bcEvent.word+75).map(compact),
    ALL5mirror:true,onlyPublicKeys:true,carrierTagsNeverLoaded:true,
    sourceReadOwner:'stack:Y',BCtargetOwner:'stack:Z',zeroE7targetOwner:'stack:Y',
    carrierIdentityNotValueProvenance:true,display:c.displayText(),
    endP9:rawRegister(c,9)};
  hashes();if(log)console.log(JSON.stringify(report));
  return {report,events,cells,records,...(all5?{
    fullPrepared,fullSeeded,landmarks,fullEnd:fullState(c),tagsEnd:fullTags(tags)}:{})};
}
if(require.main===module) {
  if(process.argv.includes('--mode-repair-proof-input'))
    console.log(JSON.stringify(run({log:false,all5:true,modeRepair:true})));
  else if(process.argv.includes('--all5-proof-input')) console.log(JSON.stringify(run({log:false,all5:true})));
  else if(process.argv.includes('--proof-input')) console.log(JSON.stringify(run({log:false})));
  else run();
}
module.exports={run,initialTags};
