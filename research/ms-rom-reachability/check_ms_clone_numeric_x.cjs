#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_clone_load_x.cjs');
const {checkClones,release}=require('./check_ms_marker_clone_w.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {createHash}=require('node:crypto');
const m='0000F0000000',g='958912345678',zero='000000000000';
const upper=['P7','P8','P9','P10'];
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q',...upper];
function normalization(word) {
  assert.match(word,/^[09][0-9]{2}[09][1-9][0-9]{7}$/);
  const z=word.slice(4).match(/0*$/)[0].length,small=word[0]==='0'&&Number(word.slice(0,3))<=7;
  const cuts=small?Math.min(z,7-Number(word.slice(0,3))):z;
  const seq='EE E3 91 92 93 94 95 98 9A 93 94 95 98 9A E4 DE'.split(' ').map(x=>parseInt(x,16));
  seq.push(...(word[0]==='9'?[0xD9]:small?[0xD0,0xF2]:[0xD0]));
  for(let i=0;i<cuts+1;i++)seq.push(0xF3,0xF7,0xF1);
  for(let i=0;i<8-cuts;i++)seq.push(0xF4,0xF6);
  seq.push(0xF4,0xEA,0xEC);
  assert.equal(seq.length,39+cuts+Number(small));
  return {seq,z,cuts,small};
}
function check(r,{unsafe=false}={}) {
  const es=r.traced.events,ww=r.traced.writes,source=r.beforeRegisters[2],stage='clone-load-x';
  assert.equal(r.options.tailActions,undefined);assert.ok([undefined,'8'].includes(r.options.sourceKey));
  const clones=checkClones(r);assert.equal(clones.length,1);
  assert.equal(r.result.stoppedOnGuard,true);assert.ok(r.result.attempts>=1&&r.result.attempts<=3);
  assert.equal(clones[0].stage,'clone-swap-'+(r.result.attempts-1));
  assert.deepEqual(r.result.displays,[...Array(r.result.attempts-1).fill(','),'-1,2345678-42']);
  const start=es.find(e=>e.stage===stage&&e.ring);assert.ok(start);
  assert.deepEqual(['X','Y','Z','T','U','V','W','Q'].map(n=>raw(start.ring[n])),[m,m,zero,g,g,g,m,g]);
  const prefixWrite=es.findIndex(e=>e.command>clones[0].command&&e.command<start.command&&e.ip===0xE7);
  const erase=checkSwapBlock(r,prefixWrite,1);
  assert.equal(erase.body[0].slot,'U');assert.equal(erase.body[0].raw,m);assert.equal(raw(erase.body[0].r,0),g);
  const helper=es.findIndex(e=>e.stage===stage&&e.ip===1);
  const hs=[1,1,1,...Array(9).fill(2),3,4,0xBA,0xCB,0xDD,0xD6];
  const actual=es.slice(helper,helper+hs.length);
  assert.deepEqual(actual.map(e=>[e.ip,e.slot]),hs.map((ip,i)=>[ip,slots[(7+i)%15]]));
  assert.ok(actual.every((e,i)=>e.command===actual[0].command+i));
  const read=actual.at(-1);assert.equal(read.slot,'W');assert.equal(raw(read.m,0),source);
  const pushAt=es.findIndex(e=>e.stage===stage&&e.command>read.command&&e.ip===0xE7);
  const push=checkSwapBlock(r,pushAt,4);
  assert.deepEqual(push.body.map(e=>e.slot),['X','Y','Z','T']);
  assert.deepEqual(push.body.map(e=>raw(e.r,0)),[source,m,m,zero]);
  const at=es.findIndex(e=>e.stage===stage&&e.command>push.body.at(-1).command&&e.ip===0xEE);
  assert.equal(es[at].slot,'X');assert.equal(es[at].raw,source);
  assert.equal(es[at].s1,13);assert.equal(es[at].r[38],12);assert.equal(es[at].r[41],15);
  assert.equal(es[at].st[36]+16*es[at].st[39],0xE3);
  const {seq,z,cuts,small}=normalization(source),norm=es.slice(at,at+seq.length+1);
  assert.deepEqual(norm.map(e=>[e.ip,e.slot]),[...seq,0x40].map((ip,i)=>[ip,slots[(3+i)%15]]));
  assert.ok(norm.every((e,i)=>e.command===norm[0].command+i));
  const fstart=norm.at(-1);
  if(source[0]==='9')assert.equal(fstart.s1,9);
  if(small)assert.equal(fstart.s1,0);
  assert.equal(raw(fstart.r,0),source);
  const form=[0x40,0x41,0x42,0x46],startSlot=slots.indexOf(fstart.slot);
  const current=()=>slots[(startSlot+form.length)%15];
  while(!['marker','Y','Z','W'].includes(current()))form.push(0xE5);
  form.push(0xE5,0xE6,0xE8,0xE7);
  const fa=at+seq.length,body=es.slice(fa,fa+form.length+1);
  assert.deepEqual(body.map(e=>[e.ip,e.slot]),[...form,0x47].map((ip,i)=>[ip,slots[(startSlot+i)%15]]));
  const result=checkSwapBlock(r,fa+form.length-1,1),dest=result.body[0].slot;
  assert.equal(raw(result.body[0].r,0),source);
  if(unsafe)assert.equal(dest,'P8');else assert.ok(['U','V'].includes(dest));
  const expected={U:g,V:g,W:m,Q:g};expected[dest]=source;
  for(const n of ['U','V','W','Q'])assert.equal(r.after[n].slice(2),expected[n]);
  for(const n of upper)assert.equal(r.after[n],n===dest?r.before[n].slice(0,2)+source:r.before[n]);
  assert.ok(ww.filter(w=>upper.includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.value===w.before||(unsafe&&w.command===result.body[0].command&&w.slot==='P8'&&w.nibble<=34)));
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[source,m,m,zero]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>[6,10,14].includes(i)?m:v));
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(e=>e.ip!==0xC9));
  return {source,attempts:r.result.attempts,zeros:z,suppressed:cuts,decimal:small,normalizerCommands:seq.length,
    formatter:result.body[0].command,destination:dest,upperPreserved:!unsafe,display:r.traced.display};
}
function main() {
  if(process.env.MS_NUMERIC_X_UNOBSERVED) {
    const o={phaseOffset:1,sourceValue:'1.2345678E-42'},r=p.run(o);check(r);
    const expected=JSON.parse(JSON.stringify(r.calc)),result=structuredClone(r.result);release(r);
    const c=p.prepare(o),plain=p.finish(c,o);c.runFrames(3);aligned(c);
    assert.deepEqual(plain,result);assert.deepEqual(JSON.parse(JSON.stringify(c)),expected);
    console.log('PASS observed/unobserved, every serialized field:',createHash('sha256').update(JSON.stringify(c)).digest('hex'));return;
  }
  if(process.env.MS_NUMERIC_X_NEGATIVE) {
    const r=p.run({phaseOffset:2,sourceValue:'-1.23E-42'});
    console.log('PASS rejected five-zero boundary:',JSON.stringify(check(r,{unsafe:true})));release(r);return;
  }
  const cases=[{phaseOffset:0,sourceValue:'-1.2345678E-42'},
    {phaseOffset:1,sourceValue:'1.2345678E-42'},
    {phaseOffset:2,sourceValue:'-8.7654321E-17'},
    {phaseOffset:2,sourceValue:'-1.234E-42'},
    {phaseOffset:2,sourceValue:'1.2345678E2',independentP8:'-8.7654321E-17',
      fullUpper:['-7.654321E23','-1E-99','8.7654321E-17','1.2345678E42']},
    {sourceValue:'-1.2345678E-42',settleFrames:12,markerFrames:8},
    {phaseOffset:1,sourceValue:'1E7'}];
  const from=Number(process.env.MS_NUMERIC_X_FROM??0),count=Number(process.env.MS_NUMERIC_X_CASES??cases.length);
  for(const o of cases.slice(from,from+count)) {
    const r=p.run(o);console.log('PASS numeric X with W held:',JSON.stringify(o),JSON.stringify(check(r)));release(r);
  }
}
if(require.main===module)main();
module.exports={check,normalization};
