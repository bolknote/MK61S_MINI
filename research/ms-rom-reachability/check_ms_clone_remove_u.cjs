#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_clone_remove_u.cjs');
const {checkClones,release}=require('./check_ms_marker_clone_w.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {createHash}=require('node:crypto');
const marker='0000F0000000',g='958912345678',zero='000000000000';
const upper=['P7','P8','P9','P10'];
function check(r) {
  const es=r.traced.events,ww=r.traced.writes,entries=checkClones(r);
  assert.equal(entries.length,1);const e=entries[0];
  const result=r.result;
  assert.equal(result.stoppedOnGuard,true);
  assert.ok(result.attempts>=1&&result.attempts<=3);
  assert.equal(e.stage,'clone-swap-'+(result.attempts-1));
  assert.deepEqual(result.displays,[...Array(result.attempts-1).fill(','),p.displayGuard]);
  assert.equal(r.traced.display,p.displayGuard);
  const plant=es.findIndex(q=>q.stage==='clone-plant-a'&&q.ip===0xD6);
  assert.ok(plant>=0);assert.equal(es[plant].slot,'X1');assert.equal(raw(es[plant].m,0),marker);
  assert.deepEqual(es.slice(plant,plant+11).map(q=>[q.ip,q.slot]),[
    [0xD6,'X1'],[0xA7,'X'],[0xE5,'Y'],[0xE6,'Z'],[0xE8,'T'],
    [0xE7,'U'],[0xA8,'V'],[0xA8,'W'],[0xA8,'Q'],[0xA9,'P7'],[0xAC,'P8']]);
  const planted=checkSwapBlock(r,plant+5,4);
  assert.deepEqual(planted.body.map(q=>raw(q.r,0)),[marker,g,r.before.V.slice(2),g]);
  const source=es.find(q=>q.stage===e.stage&&q.command>e.command&&q.ip===0xEE);
  assert.ok(source);assert.equal(source.slot,'T');assert.equal(source.raw,g);
  const erased=es.findIndex(q=>q.stage===e.stage&&q.command>source.command&&q.ip===0xE7);
  assert.ok(erased>=0);const loss=checkSwapBlock(r,erased,1);
  assert.equal(loss.body[0].slot,'U');assert.equal(loss.body[0].raw,marker);assert.equal(raw(loss.body[0].r,0),g);
  const formatter=es.slice(erased-7,erased+2);
  assert.deepEqual(formatter.map(q=>[q.ip,q.slot]),[
    [0x40,'marker'],[0x41,'control'],[0x42,'X1'],[0x46,'X'],
    [0xE5,'Y'],[0xE6,'Z'],[0xE8,'T'],[0xE7,'U'],[0x47,'V']]);
  assert.ok(formatter.every((q,i)=>q.command===formatter[0].command+i));
  assert.equal(formatter[0].s1,9);
  const stages=es.filter(q=>q.ring&&q.stage.startsWith('clone-swap-'))
    .filter((q,i,a)=>!i||q.stage!==a[i-1].stage);
  for(const q of stages) {
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(q.ring[n])),[marker,marker,zero,g]);
    assert.equal(raw(q.ring.U),marker);assert.equal(raw(q.ring.W),r.before.V.slice(2));
  }
  const end=es.find(q=>q.stage==='done'&&q.ring);assert.ok(end);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[marker,marker,zero,g]);
  for(const n of upper)assert.equal(r.after[n],r.before[n]);
  assert.ok(ww.filter(w=>upper.includes(w.slot)&&w.nibble%3===1).every(w=>w.value===w.before),
    'upper numeric and service words never temporarily change');
  assert.deepEqual(['U','V','W','Q'].map(n=>r.after[n].slice(2)),[g,g,marker,g]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>[6,10,14].includes(i)?marker:v));
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(q=>q.ip!==0xC9));
  return {entries,removeU:loss.body[0].command,display:r.traced.display,
    attempts:result?.attempts,upperPreserved:true,digest:digest(r.calc)};
}
function checkClear(r) {
  const es=r.traced.events,entries=checkClones(r),stage='clone-clear-after-remove';
  assert.equal(entries.length,1);assert.equal(r.result.stoppedOnGuard,true);
  const begin=es.find(q=>q.stage===stage&&q.ring);assert.ok(begin);
  assert.deepEqual(['X','Y','Z','T','U','V','W','Q'].map(n=>raw(begin.ring[n])),
    [marker,marker,zero,g,g,g,marker,g]);
  for(const n of upper)assert.equal(raw(begin.ring[n]),r.before[n].slice(2));
  assert.ok(r.traced.writes.filter(w=>w.command<begin.command&&upper.includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value),'the sixth word was intact before Cx');
  const at=es.findIndex(q=>q.stage===stage&&q.ip===0xE7);assert.ok(at>=0);
  const loss=checkSwapBlock(r,at,1);
  assert.equal(loss.body[0].slot,'P8');assert.equal(loss.body[0].raw,r.before.P8.slice(2));
  assert.equal(raw(loss.body[0].r,0),zero);
  assert.deepEqual(es.slice(at-7,at+2).map(q=>[q.ip,q.slot]),[
    [0x40,'Z'],[0x41,'T'],[0x43,'U'],[0x46,'V'],
    [0xE5,'W'],[0xE6,'Q'],[0xE8,'P7'],[0xE7,'P8'],[0x47,'P9']]);
  assert.equal(r.after.P8.slice(2),zero);
  for(const n of upper.filter(n=>n!=='P8'))assert.equal(r.after[n],r.before[n]);
  assert.equal(r.after.W.slice(2),marker);assert.equal(r.after.U.slice(2),g);
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.equal(r.traced.display,'0,');
  return {entries,clearDestroysSixth:loss.body[0].command,display:r.traced.display};
}
function main() {
  if(process.env.MS_REMOVE_U_NEGATIVE==='clear') {
    const o={phaseOffset:2},clone=require('./probe_ms_marker_clone_w.cjs');
    const r=clone.runPrepared(p.prepare(o),o,(c,o,record)=>{
      const result=p.finish(c,o,record);record('clone-clear-after-remove');
      c.press('Сx').runFrames(8);return result;
    });
    console.log('PASS rejected Cx after U removal:',JSON.stringify(checkClear(r)));release(r);return;
  }
  if(process.env.MS_REMOVE_U_UNOBSERVED) {
    const o={phaseOffset:2},r=p.run(o);check(r);
    const expected=JSON.parse(JSON.stringify(r.calc)),expectedResult=structuredClone(r.result);
    const expectedDigest=digest(r.calc);release(r);
    const c=p.prepare(o),result=p.finish(c,o);c.runFrames(3);aligned(c);
    assert.deepEqual(result,expectedResult);assert.deepEqual(JSON.parse(JSON.stringify(c)),expected);
    assert.equal(digest(c),expectedDigest);
    console.log('PASS adaptive observed/unobserved, every serialized data field:',
      createHash('sha256').update(JSON.stringify(c)).digest('hex'));return;
  }
  const cases=[{},{phaseOffset:1},{phaseOffset:2},
    {phaseOffset:2,independentP8:'-8.7654321E-17',
      fullUpper:['-7.654321E23','-1E-99','8.7654321E-17','1.2345678E42']},
    {settleFrames:12,markerFrames:8}];
  const from=Number(process.env.MS_REMOVE_U_FROM??0),count=Number(process.env.MS_REMOVE_U_CASES??cases.length);
  for(const o of cases.slice(from,from+count)) {
    const r=p.run(o);console.log('PASS W clone and U removal:',JSON.stringify(o),JSON.stringify(check(r)));release(r);
  }
}
if(require.main===module)main();
module.exports={check,checkClear};
