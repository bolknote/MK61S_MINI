#!/usr/bin/env node
'use strict';
// Rejected local continuations, derived from the TWO alignments in native R.
// A translated final permutation is not enough: the initial D3/37 must
// place the five D4 buffer reads on the intended pages as well.
const assert=require('node:assert/strict');
const p=require('./probe_ms_shifted_swap.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const words=['U','V','W','Q','P7','P8','P9','P10'];
const options={phaseOffset:2,values:['11','22','33','-1E-99'],stress:true,save:false};
function checkRotation(r) {
  const es=r.traced.events.filter(e=>e.stage==='shifted-swap');
  const di=es.findIndex(e=>e.otherChips?.[4].ip===0xD4);assert.ok(di>0);
  const initial=es.slice(0,di),start=initial.findLastIndex(e=>e.otherChips?.[4].ip===0xD3);
  assert.ok(start>=0);const align=initial.slice(start),s=align.map(e=>e.otherChips[4]);
  assert.equal(s[0].ip,0xD3);assert.equal(s.at(-1).ip,0x27);assert.equal(s.at(-1).slot,'control');
  const waits=s.slice(1,-1);assert.ok(waits.length>0&&waits.every(e=>e.ip===0x37));
  assert.equal(waits.at(-1).slot,'marker');assert.equal(waits.at(-1).m[22],15);
  assert.ok(waits.slice(0,-1).every(e=>e.m[22]!==15));
  assert.ok(align.every((e,i)=>e.command===align[0].command+i));
  assert.deepEqual(es.slice(di,di+5).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    ['X1','X','Y','Z','T'].map(n=>[0xD4,n]));
  const ri=es.findIndex((e,i)=>i>di&&e.otherChips?.[4].ip===0x3A);assert.ok(ri>di);
  const rotate=es.slice(ri,ri+5),before=rotate[0].ring,after=structuredClone(before),visible=['X','Y','Z','T'];
  assert.deepEqual(rotate.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [[0x3A,'X'],[0x3A,'Y'],[0x3A,'Z'],[0x2A,'T'],[0x39,'U']]);
  // C/B were loaded BEFORE the first D3/37 alignment. The output is
  // therefore NOT necessarily a rotation of the current visible words!
  // Three 3A commands emit the three ST lanes; final 2A emits A (old C).
  const chip=rotate[0].otherChips[4];
  for(let i=0;i<4;i++)for(let j=0;j<12;j++)after[visible[i]][1+3*j]=i===3?chip.r[3*j]:chip.st[3*j+i];
  assert.deepEqual(rotate[4].ring,after,'all 630 tetras: buffered output to visible pages, not lower-Ms rotation');
  const cSource=r.options.lifts===1?'U':'V',bSource=r.options.lifts===1?'V':'W';
  assert.equal(raw(chip.r,0),r.before[cSource].slice(2));
  assert.equal(raw(chip.st,0),r.before[bSource].slice(2));
  const writes=r.traced.writes.filter(w=>w.command>=rotate[0].command&&w.command<rotate[4].command);
  assert.equal(writes.length,48);
  assert.ok(writes.every(w=>w.chip===4&&visible.includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
  return {firstAlign:s.map(e=>e.slot),buffer:es[di].command,rotation:rotate[0].command,
    sources:{X:bSource,T:cSource},output:visible.map(n=>raw(after[n]))};
}
function main() {
  for(const lifts of [1,2]) {
    const r=p.run({...options,lifts,sourceKey:['F',',']});
    const alignment=checkRotation(r);
    assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterRegisters,r.beforeRegisters);assert.deepEqual(r.afterProgram,r.beforeProgram);
    assert.deepEqual(r.traced.writes.filter(w=>words.includes(w.slot)&&w.nibble%3===1&&w.before!==w.value),[]);
    console.log('PASS rejected lower rotation:',JSON.stringify({marker:lifts===1?'Y':'Z',...alignment}));
    r.traced.events.length=0;r.traced.writes.length=0;
  }
  for(const sourceKey of [['Сx'],['K','5'],['F','+']]) {
    const r=p.run({...options,lifts:1,sourceKey});
    assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterRegisters,r.beforeRegisters);assert.deepEqual(r.afterProgram,r.beforeProgram);
    assert.deepEqual(r.traced.writes.filter(w=>words.includes(w.slot)&&w.nibble%3===1&&w.before!==w.value),[]);
    const writes=r.traced.events.filter(e=>e.stage==='shifted-swap'&&e.ip===0xE7);
    assert.ok(writes.length>0&&writes.every(e=>e.slot==='X'&&e.nextIp===0x47));
    console.log('PASS rejected single-U preparation:',JSON.stringify({sourceKey,actual:writes.map(e=>[e.command,e.slot,raw(e.r,0)])}));
    r.traced.events.length=0;r.traced.writes.length=0;
  }
  console.log('LIMIT: these specific visible-marker preparations do not rotate lower Ms or replace U. This is NOT an impossibility proof for other ROM entrances.');
}
if(require.main===module)main();
module.exports={checkRotation};
