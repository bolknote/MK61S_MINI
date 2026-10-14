#!/usr/bin/env node
'use strict';
// First native BB/BC witness: public arithmetic preparation, direct D2
// address and two reads of P9. Fresh unobserved ALL5 mirror after each stage.
// This captures real per-tick primary inputs/outputs for independent replay.
// No setters, injected symbolic packet, ROM/IP/return changes or live UI.
const assert = require('node:assert/strict');
const {setup, aligned, rawRegister, dump, sample, hashes} =
  require('./cache-bc-head93-indirect-ghost-native.cjs');
const extra = {U:[2,202],V:[2,244],W:[2,34],Q:[2,76],
  P7:[1,118],P8:[1,160],P9:[1,202],P10:[1,244]};
// Phase1 STACK_ADDRESSES/PERMUTATIONS from the hashed stock reference.
const visibleStack = {x:[5,34],y:[4,34],z:[3,34],t:[2,118],x1:[2,160]};
const rawWord = (c,chip,end) => Array.from({length:12},(_,i)=>
  c.memoryForChip(chip)[end-3*i].toString(16).toUpperCase()).join('');
const primary = c => {
  const p=c.ik1302;
  return {r:p.r.slice(),st:p.stack.slice(),m:p.memory.slice(),
    s:p.s,s1:p.s1,l:p.l,t:p.t,carry:p.carry};
};
function data(c) {
  assert.equal(c.ir2a.tickIndex,84);
  return {program:Array.from({length:105},(_,i)=>c.readCommand(i)),
    registers:Array.from({length:15},(_,i)=>rawRegister(c,i)),
    stack:Object.fromEntries(Object.entries(visibleStack).map(([n,[chip,end]])=>
      [n,rawWord(c,chip,end)])),
    ms:Object.fromEntries(Object.entries(extra).map(([n,[chip,end]])=>
      [n,Array.from({length:14},(_,i)=>c.memoryForChip(chip)[end+6-3*i]
        .toString(16).toUpperCase()).join('')])),
    display:c.displayText(),pc:c.programCounter()};
}
const changed = (before,after) => ({
  program:before.program.flatMap((v,i)=>v===after.program[i]?[]:
    [{address:i,before:v,after:after.program[i]}]),
  registers:before.registers.flatMap((v,i)=>v===after.registers[i]?[]:
    [{register:i,before:v,after:after.registers[i]}]),
  ms:Object.keys(before.ms).flatMap(n=>before.ms[n]===after.ms[n]?[]:
    [{word:n,before:before.ms[n],after:after.ms[n]}]),
  stack:Object.keys(before.stack).flatMap(n=>before.stack[n]===after.stack[n]?[]:
    [{word:n,before:before.stack[n],after:after.stack[n]}]),
});
function run({log=true}={}) {
  hashes(); const c=setup(true,'10',3,false,true),plain=setup(true,'10',3,false,true);
  assert.deepEqual(dump(c),dump(plain));
  const before=data(c),firstPrepared=sample(c);
  const keys=['П→X','9'];
  for(const x of [c,plain]) {x.pressSequence(keys).runFrames(8);aligned(x);}
  assert.deepEqual(dump(c),dump(plain));
  const seeded=data(c),seedState=sample(c);
  assert.deepEqual(seedState.ST2,[0,2,13],'FIRST read constructs actual saved0/2/D');
  assert.equal(seedState.ip,0x35);
  const original=c.tick.bind(c),records=[];
  let active=false,done=false,record=null,words=0,bb=0,bc=0;
  c.tick=function() {
    const p=this.ik1302,j=p.tickIndex;
    if(j===0) {
      words++;const s=sample(this);
      if(s.ip===0xBB)bb++;if(s.ip===0xBC)bc++;
      if(!active&&!done&&s.ip===0xA3&&s.vector===0xCC&&s.C[0]===0
          &&s.C[1]===2&&s.C[2]===13&&s.S1===9
          &&s.tags.join()===[0x93,0xE5,0xAD].join()) active=true;
      if(active) {record={word:words-1,ip:s.ip,ir2aTick:this.ir2a.tickIndex,before:primary(this),
        keysX:[],keysY:[],serial:[],emitted:[]};records.push(record);}
    }
    const observe=active;
    if(observe) {record.keysX.push(p.keyX);record.keysY.push(p.keyY);}
    const result=original();
    if(observe) {
      record.serial.push(this.ir2b.output);record.emitted.push(p.output);
      if(p.tickIndex===0) {
        record.after=primary(this);
        if(record.ip===0xBE) {active=false;done=true;}
      }
    }
    return result;
  };
  for(const x of [c,plain]) {x.pressSequence(keys).runFrames(8);aligned(x);}
  assert.deepEqual(dump(c),dump(plain),'SECOND entire suffix fresh unobserved ALL5 mirror');
  const after=data(c);
  assert.equal(bb,1);assert.equal(bc,1);assert.ok(done&&records.length);
  assert.equal(records[0].ip,0xA3);assert.equal(records.at(-1).ip,0xBE);
  assert.ok(records.every((e,i)=>e.keysX.length===42&&e.serial.length===42
    &&(!i||e.word===records[i-1].word+1)));
  const bbr=records.find(e=>e.ip===0xBB),bcr=records.find(e=>e.ip===0xBC);
  const source=bbr.before.r.filter((_,i)=>i%3===1);
  const output=bcr.emitted.filter((_,i)=>i%3===1);
  const targetBefore=bcr.before.m.filter((_,i)=>i%3===1);
  assert.deepEqual(output,source,'true BC emits all14 native B tetras including3/A');
  assert.deepEqual(source.slice(-2),[3,10]);
  assert.deepEqual(source.slice(0,12),[3,0,0,0,0,0,0,1,0,0,0,6]);
  assert.deepEqual(targetBefore.slice(0,12),output.slice(0,12),
    'this FIRST witness numerically rewrites equal data; not a nontrivial bank exchange');
  assert.equal(bcr.after.r[36]+16*bcr.after.r[39],0x93);
  assert.equal(records.length,79,'fixed first witness has79 consecutive original words');
  const actualPostBE=records.at(-1).after.r[36]+16*records.at(-1).after.r[39];
  assert.equal(actualPostBE,0x63,'native nonzero RAW5 does NOT take the clean35 subset');
  const seedChanges=changed(before,seeded),secondChanges=changed(seeded,after);
  for(const changes of [seedChanges,secondChanges])
    for(const area of ['program','registers','ms'])
      assert.deepEqual(changes[area],[],'this witness leaves endpoint '+area+' unchanged');
  assert.deepEqual(secondChanges.stack,[
    {word:'y',before:'600010000003',after:'000000000000'},
    {word:'t',before:'093050000000',after:'600010000003'},
    {word:'x1',before:'000000000000',after:'093050000000'},
  ]);
  const report={firstPrepared,seedState,firstRead:keys,secondRead:keys,
    savedHeaderConstructedByKeys:true,nativeBB:bb,nativeBC:bc,words,
    primaryWindow:records.length,BCsource14:source,BCbefore14:targetBefore,BCoutput14:output,
    BCtrueReturn:0x93,actualPostBE,
    beforeDisplay:before.display,seedDisplay:seeded.display,afterDisplay:after.display,
    seedChanges,secondChanges,
    observerIndependentALL5:true,nativeOnlyPublicKeys:true,
    fullK2:false,physicalInverse:false};
  hashes();if(log)console.log(JSON.stringify(report));
  return {report,records,before,seeded,after};
}
if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(run({log:false})));
  else run();
}
module.exports={run};
