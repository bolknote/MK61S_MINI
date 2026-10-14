#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_quiet_upper.cjs');
const {check:checkPair,prefixView,store,swap}=require('./check_ms_quiet_upper.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {release}=require('./check_ms_marker_clone_w.cjs');
const tail=[['F','В↑'],['X→П',',']];
function check(r) {
  assert.equal(r.options.phaseOffset,2);assert.deepEqual(r.options.afterQuiet,p.actions({upperTail:tail}));
  const prefix=prefixView(r,5);checkPair(prefix);
  const a=r.before.P7.slice(2),c=r.before.P9.slice(2);assert.notEqual(a,c);
  const es=r.traced.events,read=es.find(e=>e.stage==='clone-quiet-after-5'&&e.ip===0xEE);
  assert.ok(read);assert.equal(read.slot,'P7');assert.equal(raw(read.m),a);
  assert.deepEqual([read.s1,read.r[23],read.r[26],read.r[29],...read.sp],[14,0,0,0,0xF0,0x8E,0x9A]);
  const ips=[0xEE,0xF0,0xE0,0xA7,0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9];
  const names=['P7','P8','P9','P10','marker','control','X1','X','Y','Z','T','U'];
  const at=es.indexOf(read);
  assert.deepEqual(es.slice(at,at+ips.length).map(e=>[e.ip,e.slot]),ips.map((ip,i)=>[ip,names[i]]));
  const pushed=swap(r,read.command+7,['X','Y','Z','T']);assert.equal(raw(pushed.body[0].r,0),a);
  const returned=es.filter(e=>e.stage===read.stage&&e.ip===0xEE&&e.command>read.command);assert.equal(returned.length,1);
  assert.equal(returned[0].slot,'P8');assert.equal(raw(returned[0].m),c);
  const replace=es.find(e=>e.stage===read.stage&&e.ip===0xE7&&e.command>returned[0].command);assert.ok(replace);
  assert.equal(replace.slot,'X');assert.equal(raw(replace.m),a);assert.equal(raw(replace.r,0),c);
  swap(r,replace.command,['X']);
  const saved=store(r,6,c,'P7','P8');assert.notEqual(saved.value,a);
  assert.deepEqual(r.after,prefix.after);
  assert.deepEqual(r.afterRegisters,prefix.afterRegisters.map((v,i)=>i===4?c:v));
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {readFifth:read.command,pushFifth:pushed.body[0].command,overwriteX:replace.command,
    stored:saved.value,wanted:a,MsHeld:true,successfulFifthBackup:false};
}
if(require.main===module) {
  const r=p.run({phaseOffset:2,upperTail:tail});console.log('PASS negative last-X readout:',JSON.stringify(check(r)));release(r);
}
module.exports={check};
