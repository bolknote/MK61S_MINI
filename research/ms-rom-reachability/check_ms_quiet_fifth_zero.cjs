#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_quiet_fifth_zero.cjs');
const upper=require('./probe_ms_quiet_upper.cjs');
const {check:checkPair,prefixView,store,swap}=require('./check_ms_quiet_upper.cjs');
const {normalization}=require('./check_ms_clone_numeric_x.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {release}=require('./check_ms_marker_clone_w.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {createHash}=require('node:crypto');
const ms=['U','V','W','Q','P7','P8','P9','P10'];
const zero='000000000000';

function zeroReturn(r,index) {
  const es=r.traced.events,read=es[index];assert.equal(read.ip,0xEE);assert.equal(read.slot,'P8');assert.equal(raw(read.m),zero);
  assert.deepEqual([read.s1,read.r[38],read.r[41],read.sp[0]],[13,12,15,0xE3]);
  // The normalizer happens to follow the same 47-command path as 1, but
  // zero takes 43 instead of 42 in the proved return prefix.
  const seq=[...normalization('000010000000').seq,0x40,0x41,0x43,0x46,...Array(7).fill(0xE5),0xE6,0xE8,0xE7,0x47];
  const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  assert.deepEqual(es.slice(index,index+seq.length).map(e=>[e.ip,e.slot]),seq.map((ip,i)=>[ip,slots[(12+i)%15]]));
  const written=es[index+seq.length-2];assert.equal(raw(written.r,0),zero);
  swap(r,written.command,['P8']);
  assert.ok(r.traced.writes.filter(w=>w.command>=read.command&&w.command<written.command).every(w=>w.before===w.value),
    'the zero normalizer does not change ring data on any chip');
  return written.command;
}

function check(r) {
  assert.deepEqual(r.options.afterQuiet,upper.actions(p.options(r.options)));
  const prefix=prefixView(r,5);checkPair(prefix);
  const a=r.before.P7.slice(2),b=r.before.P8.slice(2),c=r.before.P9.slice(2),d=r.before.P10.slice(2);
  assert.notEqual(a,zero); // The negative-store control must remain discriminating.
  const es=r.traced.events,clear=es.filter(e=>e.stage==='clone-quiet-after-5'&&e.ip===0xE7);
  assert.equal(clear.length,1);assert.equal(clear[0].slot,'P8');assert.equal(raw(clear[0].r,0),zero);
  swap(r,clear[0].command,['P8']);
  const reads=es.filter(e=>e.stage==='clone-quiet-after-7'&&e.ip===0xEE);assert.equal(reads.length,2);
  const first=reads[0];assert.equal(first.slot,'P7');assert.equal(raw(first.m),a);
  assert.deepEqual([first.s1,first.r[23],first.r[26],first.r[29],...first.sp],[14,0,0,0,0xF0,0x8E,0x9A]);
  const ips=[0xEE,0xF0,0xE0,0xA7,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9];
  const names=['P7','P8','P9','P10','marker','control','X1','X','Y','Z','T','U'];
  const at=es.indexOf(first);
  assert.deepEqual(es.slice(at,at+ips.length).map(e=>[e.ip,e.slot]),ips.map((ip,i)=>[ip,names[i]]));
  const pushed=swap(r,first.command+7,['X','Y','Z','T']);assert.equal(raw(pushed.body[0].r,0),a);
  const returned=zeroReturn(r,es.indexOf(reads[1]));
  const beforeStore=es.find(e=>e.stage==='clone-quiet-after-8'&&e.ring);assert.ok(beforeStore);
  assert.equal(raw(beforeStore.ring.X),a,'fifth word persists after the complete last-X return');
  const negative=!!r.options.unsplitStore,index=negative?8:9;
  const saved=store(r,index,negative?zero:a,'P7',negative?'P8':'X');
  const storeReads=es.filter(e=>e.stage==='clone-quiet-after-'+index&&e.ip===0xEE&&e.command>saved.write);
  assert.equal(storeReads.length,1);zeroReturn(r,es.indexOf(storeReads[0]));
  assert.deepEqual(r.after,{...prefix.after,P8:prefix.after.P8.slice(0,2)+zero});
  assert.deepEqual(r.afterRegisters,prefix.afterRegisters.map((v,i)=>i===4?(negative?zero:a):v));
  const begin=es.find(e=>e.stage==='clone-quiet-after-5');
  assert.ok(r.traced.writes.filter(w=>w.command>=begin.command&&ms.includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value||w.command===clear[0].command&&w.slot==='P8'&&w.nibble<=34),
    'only the already backed-up sixth physical word is cleared; all other Ms data is held');
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[a,c,b,'14'+b[2]+'000000000']);
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {phase:r.options.phaseOffset,cleared:clear[0].command,readFifth:first.command,protectedReturn:returned,
    store:saved,copies:[r.afterRegisters[4],r.afterRegisters[2],r.afterRegisters[3]],untouchedEighth:d,
    successfulFifthBackup:!negative,display:r.traced.display};
}

if(require.main===module) {
  const cases=[{phaseOffset:2},
    {phaseOffset:0,fullUpper:['-7.654321E23','1.2345678E42','8.7654321E-17','-1E-99']},
    {phaseOffset:1,fullUpper:['-1E-99','-1.23E-42','3333','4444']}];
  if(process.env.MS_FIFTH_ZERO_UNOBSERVED) {
    const o=cases[0],r=p.run(o);check(r);const expected=JSON.parse(JSON.stringify(r.calc)),result=structuredClone(r.result);release(r);
    const plain=p.prepare(o),actual=p.finish(plain,o);plain.runFrames(3);aligned(plain);
    assert.deepEqual(actual,result);assert.deepEqual(JSON.parse(JSON.stringify(plain)),expected);
    console.log('PASS fifth-zero complete observed/unobserved state:',createHash('sha256').update(JSON.stringify(plain)).digest('hex'));
  } else if(process.env.MS_FIFTH_ZERO_NEGATIVE) {
    const r=p.run({...cases[0],unsplitStore:true});console.log('PASS negative unsplit store:',JSON.stringify(check(r)));release(r);
  } else {
    const from=Number(process.env.MS_FIFTH_ZERO_FROM??0),count=Number(process.env.MS_FIFTH_ZERO_CASES??cases.length);
    for(const o of cases.slice(from,from+count)) {const r=p.run(o);console.log('PASS fifth word protected by zero:',JSON.stringify(check(r)));release(r);}
  }
}
module.exports={check,zeroReturn};
