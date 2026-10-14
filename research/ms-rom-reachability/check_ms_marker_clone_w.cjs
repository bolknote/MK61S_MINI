#!/usr/bin/env node
'use strict';
// Exact native marker-cloning block and deliberately separate whole-entry
// preservation checks. Neither alone claims a phase-independent writer.
const assert=require('node:assert/strict');
const p=require('./probe_ms_marker_clone_w.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const marker='0000F0000000',zero='000000000000',g='958912345678';
const upper=['P7','P8','P9','P10'];
const guarded=o=>({values:['111','222','-1.2345678E-42','444'],...o});
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const release=r=>{r.traced.events.length=0;r.traced.writes.length=0;};
function checkClones(r) {
  const es=r.traced.events,entries=es.filter(e=>e.stage.startsWith('clone-')&&e.ip===0xE9&&e.slot==='W');
  assert.ok(entries.length,'must really execute E9(W)');
  const paths=[];
  for(const e of entries) {
    const index=es.indexOf(e);
    const gate=es.slice(Math.max(0,index-17),index).findLast(q=>q.ip===0x9C&&[4,1].every((v,i)=>q.r[30+3*i]===v));
    assert.ok(gate&&['V','Q'].includes(gate.slot));
    const start=slots.indexOf(gate.slot),seq=[0x9C,0x9E,0x9F,0xA0];
    const current=()=>slots[(start+seq.length)%15];
    while(current()!=='marker')seq.push(0xE5);
    seq.push(0xE5,0xE6,0xED,0xEE,0xA1);
    while(current()!=='U')seq.push(0xE5);
    seq.push(0xE5,0xE6,0xE9);
    const block=es.slice(es.indexOf(gate),index+2);
    assert.deepEqual(block.map(q=>[q.ip,q.slot]),[...seq,0xA2].map((ip,i)=>[ip,slots[(start+i)%15]]));
    assert.ok(block.every((q,i)=>q.command===gate.command+i));
    assert.ok(gate.m[34]>=(gate.m[31]===15?1:7));
    const source=block.find(q=>q.ip===0xEE);assert.equal(source.slot,'X');assert.equal(source.raw,marker);
    assert.equal(raw(e.r,0),marker);
    const expected=structuredClone(e.ring);
    for(let j=0;j<12;j++)expected.W[1+3*j]=source.m[1+3*j];
    assert.deepEqual(block.at(-1).ring,expected,'all 630 tetras after the single copy');
    const writes=r.traced.writes.filter(w=>w.command===e.command);
    assert.equal(writes.length,12);
    assert.ok(writes.every(w=>w.chip===3&&w.slot==='W'&&w.nibble%3===1&&w.nibble<=34));
    const back=es.slice(index+1,index+8);
    assert.deepEqual(back.map(q=>[q.ip,q.slot]),[
      ...['Q','P7','P8','P9','P10','marker'].map(n=>[0xA2,n]),[0xA3,'control']]);
    paths.push({stage:e.stage,command:e.command,control:gate.slot,commands:seq.length});
  }
  return paths;
}
function checkSafe(r) {
  const entries=checkClones(r),es=r.traced.events;
  for(const n of upper)assert.equal(r.after[n],r.before[n],n+' end preservation');
  assert.ok(r.traced.writes.filter(w=>upper.includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value),'upper data/service never even temporarily changed');
  assert.equal(r.after.U.slice(2),marker);assert.equal(r.after.W.slice(2),marker);
  assert.equal(r.after.V.slice(2),g);assert.equal(r.after.Q.slice(2),g);
  const keyIndex={'1':1,'6':6,'В↑':14};
  const scratch=[9,keyIndex[r.options.sourceKey??'1'],...(r.options.sourceMirror?[keyIndex[r.options.sourceMirror]]:[])];
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>scratch.includes(i)?marker:v));
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(e=>e.ip!==0xC9));
  const returns=[];
  for(const e of entries) {
    const copy=es.find(q=>q.command===e.command);
    const gate=es.find(q=>q.command>copy.command&&q.stage===copy.stage&&q.ip===0x9C&&q.slot==='Z');
    assert.ok(gate);assert.equal(gate.nextIp,0x9D);assert.equal(gate.raw,zero);
    const at=es.indexOf(gate),route=es.slice(at,at+6);
    assert.deepEqual(route.map(q=>[q.ip,q.slot]),[[0x9C,'Z'],[0x9D,'T'],[0x97,'U'],[0x99,'V'],[0x9B,'W'],[0x9C,'Q']]);
    assert.equal(route.at(-1).nextIp,0x9E);
    const read=es.find(q=>q.command>gate.command&&q.stage===copy.stage&&q.ip===0xEE);
    assert.equal(read.slot,'T');assert.equal(read.raw,zero);
    const write=es.findIndex(q=>q.command>read.command&&q.stage===copy.stage&&q.ip===0xE7);
    const out=checkSwapBlock(r,write,1);
    assert.equal(out.body[0].slot,'X');assert.equal(raw(out.body[0].r,0),zero);
    returns.push({gate:gate.command,formatter:out.body[0].command});
  }
  return {entries,returns,upperPreserved:true,digest:digest(r.calc)};
}
function checkFormatterLoss(r) {
  const entries=checkClones(r),es=r.traced.events;
  const at=es.findIndex(e=>e.stage.startsWith('clone-')&&e.ip===0xE7&&e.slot==='P8'&&e.nextIp===0x47);
  assert.ok(at>=0);const loss=checkSwapBlock(r,at,1);
  assert.equal(loss.body[0].raw,r.before.P8.slice(2));assert.equal(raw(loss.body[0].r,0),marker);
  return {entries,formatterLoss:loss.body[0].command};
}
function checkClearLoss(r) {
  const entries=checkClones(r),es=r.traced.events;
  const at=es.findIndex(e=>e.stage==='clone-cx'&&e.ip===0xE7&&e.slot==='P8'&&e.nextIp===0x47);
  assert.ok(at>=0);const loss=checkSwapBlock(r,at,1);
  assert.equal(loss.body[0].raw,r.before.P8.slice(2));assert.equal(raw(loss.body[0].r,0),zero);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  return {entries,clearDestroysSixth:loss.body[0].command};
}
function checkWrongSource(r) {
  assert.equal(r.options.phaseOffset,2);
  const es=r.traced.events,rows=es.filter(e=>e.stage==='clone-source');
  const read=rows.find(e=>e.ip===0xD6);assert.equal(read.slot,'marker');
  assert.equal(raw(read.m,0),r.beforeRegisters[8]);
  const at=es.findIndex(e=>e.stage==='clone-source'&&e.ip===0xE7&&e.slot==='Q');
  const push=checkSwapBlock(r,at,4);
  assert.deepEqual(push.body.map(e=>e.slot),['Q','P7','P8','P9']);
  assert.equal(raw(push.body[0].r,0),r.beforeRegisters[8]);
  assert.equal(push.body[3].raw,r.before.P9.slice(2));
  assert.equal(es.filter(e=>e.stage.startsWith('clone-')&&e.ip===0xE9&&e.slot==='W').length,0);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  return {wrongSource:read.command,push:push.body[0].command,notAClone:true};
}
function checkMirrored(r,{expectClone=true}={}) {
  assert.equal(r.options.sourceKey,'В↑');assert.equal(r.options.sourceMirror,'6');
  const es=r.traced.events,reads=[];
  for(const stage of ['clone-source','clone-source-1']) {
    const read=es.find(e=>e.stage===stage&&e.ip===0xD6);
    assert.ok(read&&['T','P9'].includes(read.slot));assert.equal(raw(read.m,0),marker);
    const at=es.findIndex(e=>e.stage===stage&&e.ip===0xE7);
    const push=checkSwapBlock(r,at,4);
    assert.deepEqual(push.body.map(e=>e.slot),['X','Y','Z','T']);assert.equal(raw(push.body[0].r,0),marker);
    reads.push({stage,slot:read.slot,command:read.command});
  }
  if(expectClone)return {...checkSafe(r),reads};
  assert.equal(es.filter(e=>e.stage.startsWith('clone-')&&e.ip===0xE9&&e.slot==='W').length,0);
  for(const n of upper)assert.equal(r.after[n],r.before[n]);
  assert.ok(r.traced.writes.filter(w=>upper.includes(w.slot)&&w.nibble%3===1).every(w=>w.value===w.before));
  assert.equal(r.after.U.slice(2),marker);assert.equal(r.after.W.slice(2),r.before.V.slice(2));
  assert.equal(r.after.V.slice(2),g);assert.equal(r.after.Q.slice(2),g);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>[6,9,14].includes(i)?marker:v));
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {reads,upperPreserved:true,notCloned:true,digest:digest(r.calc)};
}
function main() {
  if(process.env.MS_CLONE_MIRROR) {
    const phaseOffset=Number(process.env.MS_CLONE_MIRROR)-1;
    const r=p.run(guarded({phaseOffset,sourceKey:'В↑',sourceMirror:'6',sourceCopies:2,swaps:2}));
    console.log('PASS mirrored source, conditional clone:',JSON.stringify(checkMirrored(r,{expectClone:phaseOffset!==2})));release(r);return;
  }
  if(process.env.MS_CLONE_NEGATIVE==='clear') {
    const r=p.run(guarded({phaseOffset:1,sourceCopies:2,swaps:1,
      tailActions:[['clone-cx',['Сx']],['clone-digit',['1']],['clone-write',['↔']]]}));
    console.log('PASS rejected clear/digit continuation:',JSON.stringify(checkClearLoss(r)));release(r);return;
  }
  if(process.env.MS_CLONE_NEGATIVE==='formatter') {
    const r=p.run({});console.log('PASS rejected unguarded return:',JSON.stringify(checkFormatterLoss(r)));release(r);return;
  }
  if(process.env.MS_CLONE_NEGATIVE==='source') {
    const r=p.run(guarded({phaseOffset:2,sourceCopies:2,swaps:1}));
    console.log('PASS rejected physical P8 source:',JSON.stringify(checkWrongSource(r)));release(r);return;
  }
  const cases=[guarded({}),guarded({phaseOffset:1,sourceCopies:2,swaps:1}),
    guarded({phaseOffset:1,sourceCopies:2,swaps:1,independentP8:'-8.7654321E-17',
      fullUpper:['-1E-99','8.7654321E76','-7.654321E-23','1.2345678E42']})];
  const from=Number(process.env.MS_CLONE_FROM??0),count=Number(process.env.MS_CLONE_CASES??cases.length);
  for(const o of cases.slice(from,from+count)) {
    const r=p.run(o);console.log('PASS conditional safe W clone:',JSON.stringify(o),JSON.stringify(checkSafe(r)));release(r);
  }
}
if(require.main===module)main();
module.exports={guarded,checkClones,checkSafe,checkFormatterLoss,checkClearLoss,checkWrongSource,checkMirrored,release};
