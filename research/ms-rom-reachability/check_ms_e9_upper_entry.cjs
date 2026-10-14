#!/usr/bin/env node
'use strict';
// Native reachability of the single upper E9 writer, with an explicit
// regression assertion for the earlier destructive P8 formatter.
// This is NOT a safe upper exchange or a claim that original P8 survives.
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_marker_w.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const marker='0000F0000000',zero='000000000000';
const tailActions=Array.from({length:3},(_,i)=>['tail-swap'+i,['↔']]);
const options=o=>({...o,tailActions});
const release=r=>{r.traced.events.length=0;r.traced.writes.length=0;};
function check(r,{expectThirdSwap=(r.options.phaseOffset===2)}={}) {
  const es=r.traced.events,ww=r.traced.writes;
  const entries=es.filter(e=>e.stage.startsWith('tail-')&&e.ip===0xE9&&e.slot==='P7');
  assert.ok(entries.length,'at least one native E9(P7), not only an assumed symbolic entry');
  const path=[[0x9C,'Q'],[0x9E,'P7'],[0x9F,'P8'],[0xA0,'P9'],[0xE5,'P10'],
    [0xE5,'marker'],[0xE6,'control'],[0xED,'X1'],[0xEE,'X'],[0xA1,'Y'],
    ...['Z','T','U','V','W'].map(n=>[0xE5,n]),[0xE6,'Q'],[0xE9,'P7'],[0xA2,'P8']];
  for(const e of entries) {
    const index=es.indexOf(e),block=es.slice(index-16,index+2);
    assert.deepEqual(block.map(e=>[e.ip,e.slot]),path);
    assert.ok(block.every((e,i)=>e.command===block[0].command+i));
    assert.deepEqual([block[0].r[30],block[0].r[33]],[4,1]);
    assert.ok(block[0].m[34]>=(block[0].m[31]===15?1:7));
    assert.equal(block[0].nextIp,0x9E);
    const source=block[8];assert.equal(source.nextIp,0xA1);
    assert.equal(raw(e.r,0),source.raw);assert.equal(e.nextIp,0xA2);
    const expected=structuredClone(e.ring);
    for(let j=0;j<12;j++)expected.P7[1+3*j]=source.m[1+3*j];
    assert.deepEqual(block.at(-1).ring,expected,'E9 changes exactly 12 P7 tetras among all 630');
    const writes=ww.filter(w=>w.command===e.command);assert.equal(writes.length,12);
    assert.ok(writes.every(w=>w.chip===3&&w.slot==='P7'&&w.nibble%3===1&&w.nibble<=34));
    const request=es.find(q=>q.stage===e.stage&&q.command>e.command&&q.ip===0xA3);
    assert.equal(request?.slot,'control');
  }
  // Deliberately test the damage too. A correct E9 suffix alone must not
  // be advertised as an intact-Ms operation.
  const bad=es.findIndex(e=>e.stage==='shift-1'&&e.ip===0xE7&&e.slot==='P8'&&e.nextIp===0x47);
  assert.ok(bad>=0,'the known early loss remains visible, not omitted from the trace');
  const loss=checkSwapBlock(r,bad,1);
  assert.equal(raw(loss.body[0].r,0),zero);assert.equal(loss.body[0].raw,r.before.P8.slice(2));
  const first=es.find(e=>e.stage==='tail-swap0'&&e.ring);
  assert.equal(raw(first.ring.W),marker);assert.equal(raw(first.ring.P8),zero);
  assert.ok(ww.filter(w=>w.command>=first.command&&w.slot==='W'&&w.nibble%3===1)
    .every(w=>w.value===w.before),'the W marker survives every exchange attempt');
  if(expectThirdSwap) {
    const at=es.findIndex(e=>e.stage==='tail-swap1'&&e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='P8');
    assert.ok(at>=0,'the extra P8/P9 exchange must be traced, not declared an allowed loss');
    const block=es.slice(at,at+3),source=block[0].otherChips[4];
    assert.deepEqual(block.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x4E,'P8'],[0x2A,'P9'],[0x39,'P10']]);
    assert.equal(raw(source.r,0),r.before.P9.slice(2));
    const expected=structuredClone(block[0].ring);
    for(let j=0;j<12;j++) {
      expected.P8[1+3*j]=block[0].ring.P9[1+3*j];
      expected.P9[1+3*j]=block[0].ring.P8[1+3*j];
    }
    assert.deepEqual(block[2].ring,expected,'secondary chip exchanges exactly P8/P9, all other tetras held');
    const writes=ww.filter(w=>w.command>=block[0].command&&w.command<block[2].command);
    assert.equal(writes.length,24);assert.ok(writes.every(w=>w.chip===4&&['P8','P9'].includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
    assert.equal(r.after.P8.slice(2),r.before.P9.slice(2),'original seventh word survives, but in P8');
    assert.equal(r.after.P9.slice(2),raw(block[0].ring.P8));
    assert.ok(ww.filter(w=>w.slot==='P9'&&w.nibble%3===1&&w.before!==w.value)
      .every(w=>w.command===block[1].command));
  }
  for(const n of expectThirdSwap?['P10']:['P9','P10']) {
    assert.equal(r.after[n],r.before[n]);
    assert.ok(ww.filter(w=>w.slot===n&&w.nibble%3===1).every(w=>w.value===w.before));
  }
  assert.ok(ww.filter(w=>w.nibble%3===1&&w.nibble>=37).every(w=>w.value===w.before));
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>i===9?marker:v));
  assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {entries:entries.map(e=>({stage:e.stage,command:e.command,source:raw(e.r,0)})),
    earlyLoss:loss.body[0].command,extraThirdWordSwap:expectThirdSwap,
    upperAfter:['P7','P8','P9','P10'].map(n=>r.after[n].slice(2))};
}
function plain(o={}) {
  const c=p.prepare(o),before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  p.finish(c,options(o));c.runFrames(3);aligned(c);
  return {calc:c,before,beforeRegisters,beforeProgram,after:fullMsPages(c),afterRegisters:registers(c),afterProgram:program(c)};
}
function checkRejectedPlacement(r) {
  const es=r.traced.events,word=r.beforeRegisters[3];assert.notEqual(word,zero);
  const planted=es.findIndex(e=>e.stage==='plant-u'&&e.ip===0xE7&&e.slot==='U'&&e.nextIp===0xA8);
  assert.ok(planted>=0);const push=checkSwapBlock(r,planted,4);
  assert.equal(raw(push.body[0].r,0),marker);
  const erased=es.findIndex((e,i)=>i>planted&&e.stage==='plant-u'&&e.ip===0xE7&&e.slot==='U'&&e.nextIp===0x47);
  assert.ok(erased>=0);const loss=checkSwapBlock(r,erased,1);
  assert.equal(loss.body[0].raw,marker);assert.equal(raw(loss.body[0].r,0),word);
  assert.notEqual(r.after.W.slice(2),marker);
  for(const n of ['P7','P8','P9','P10'])assert.equal(r.after[n],r.before[n]);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  return {planted:push.body[0].command,erased:loss.body[0].command,word};
}
function checkProgramNoBypass(r) {
  assert.equal(r.options.programShift,true);assert.deepEqual(r.beforeProgram.slice(0,2),[0x68,0x50]);
  const es=r.traced.events,at=es.findIndex(e=>e.stage==='tail-run'&&e.ip===0xE7&&e.slot==='P8'&&e.nextIp===0x47);
  assert.ok(at>=0);const block=checkSwapBlock(r,at,1);
  assert.equal(block.body[0].raw,r.before.P8.slice(2));assert.equal(raw(block.body[0].r,0),zero);
  assert.equal(r.after.P8.slice(2),zero);assert.equal(r.after.W.slice(2),marker);
  assert.notDeepEqual(r.afterProgram,r.beforeProgram,'this program-mode candidate also fails program preservation');
  return {formatter:block.body[0].command,programChanges:r.afterProgram.map((v,i)=>
    v===r.beforeProgram[i]?null:[i,r.beforeProgram[i],v]).filter(Boolean)};
}
function checkD5Loop(r) {
  assert.equal(r.options.formatterBypass580,true);
  assert.deepEqual(r.after,r.before);assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters);
  const es=r.traced.events,rows=es.filter(e=>e.stage==='shift-1');
  const d5=rows.filter(e=>e.ip===0xD5);assert.ok(d5.length>3);
  assert.ok(d5.slice(1).every((e,i)=>e.command-d5[i].command===45));
  assert.ok(rows.filter(e=>e.ip===0xEE).every(e=>e.slot==='X'&&e.raw==='580010000005'));
  assert.equal(es.filter(e=>['plant-u','shift-0','shift-1'].includes(e.stage)&&[0xD6,0xE7,0xE9].includes(e.ip)).length,0);
  assert.notEqual(r.after.W.slice(2),marker);
  return {cyclesInLastStage:d5.length,period:45,source:'580010000005',markerNeverPlanted:true};
}
function main() {
  if(process.env.MS_E9_UPPER_NEGATIVE==='visible') {
    for(const visibleSource of ['-1.2345678E-42','1.2345678E42']) {
      const r=p.run({visibleSource});console.log('PASS rejected nonzero visible source:',JSON.stringify(checkRejectedPlacement(r)));release(r);
    }
    return;
  }
  if(process.env.MS_E9_UPPER_NEGATIVE==='program') {
    const r=p.run({programShift:true});console.log('PASS rejected program-mode bypass:',JSON.stringify(checkProgramNoBypass(r)));release(r);return;
  }
  if(process.env.MS_E9_UPPER_NEGATIVE==='d5') {
    const r=p.run({formatterBypass580:true});console.log('PASS rejected D5 bypass:',JSON.stringify(checkD5Loop(r)));release(r);return;
  }
  const cases=[{},{phaseOffset:1},{phaseOffset:2},{phaseOffset:2,mirrorSource:false}];
  const from=Number(process.env.MS_E9_UPPER_FROM??0),count=Number(process.env.MS_E9_UPPER_CASES??cases.length);
  for(const o of cases.slice(from,from+count)) {
    const r=p.run(options(o));console.log('PASS upper E9 native entry, NOT intact exchange:',JSON.stringify(o),JSON.stringify(check(r)));
    console.log('DIGEST',digest(r.calc));release(r);
  }
}
if(require.main===module)main();
module.exports={check,options,plain,release,checkRejectedPlacement,checkProgramNoBypass,checkD5Loop};
