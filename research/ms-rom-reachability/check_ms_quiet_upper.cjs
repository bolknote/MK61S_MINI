#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_quiet_upper.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {check:checkQuiet}=require('./check_ms_clone_quiet_request.cjs');
const {release}=require('./check_ms_marker_clone_w.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {normalization}=require('./check_ms_clone_numeric_x.cjs');
const upper=['P7','P8','P9','P10'],ms=['U','V','W','Q',...upper];
const ordinary=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
const m='0000F0000000';
const stage=i=>'clone-quiet-after-'+i;

// Construct a prefix view entirely from the observer's earlier snapshot.
// This never reads or restores the live calculator and never retimes a key.
function prefixView(r,index) {
  const end=r.traced.events.find(e=>e.stage===stage(index)&&e.ring);assert.ok(end);
  const before=ringAt(r,end.command);
  return {...r,options:{...r.options,afterQuiet:r.options.afterQuiet.slice(0,index)},
    after:Object.fromEntries(ms.map(n=>[n,raw(before[n],1,14)])),
    afterRegisters:ordinary.map(n=>raw(before[n],0)),
    traced:{...r.traced,events:[...r.traced.events.filter(e=>e.command<end.command),{...end,stage:'done'}],
      writes:r.traced.writes.filter(w=>w.command<end.command)}};
}
const checkPrefix=r=>checkQuiet(prefixView(r,3));

function store(r,index,value,destination,sourceSlot='X') {
  const es=r.traced.events.filter(e=>e.stage===stage(index));
  const ds=es.filter(e=>e.ip===0xD4);assert.equal(ds.length,1);
  const write=ds[0],reads=es.filter(e=>e.ip===0xEE&&e.command<write.command);
  assert.equal(reads.length,1);const source=reads[0];
  assert.equal(source.slot,sourceSlot);assert.equal(raw(source.m),value);
  assert.equal(write.slot,destination);
  const next=r.traced.events.find(e=>e.command===write.command+1);assert.ok(next);assert.equal(next.ip,0xA5);
  const expected=ringAt(r,write.command);
  for(let j=0;j<12;j++)expected[destination][3*j]=source.m[1+3*j];
  assert.deepEqual(ringAt(r,write.command+1),expected,'exact D4 store among all 630 tetras');
  const writes=r.traced.writes.filter(w=>w.command===write.command);
  assert.deepEqual(writes.map(w=>[w.chip,w.slot,w.nibble,w.value]),
    Array.from({length:12},(_,j)=>[3,destination,3*j,source.m[1+3*j]]));
  return {source:source.command,write:write.command,destination,value};
}

function swap(r,command,targets) {
  const body=r.traced.events.filter(e=>e.command>=command&&e.command<command+targets.length);
  assert.deepEqual(body.map(e=>[e.ip,e.slot]),targets.map((n,i)=>[i?0xA8:0xE7,n]));
  const expected=ringAt(r,command);let carried=body[0].r.filter((_,i)=>i%3===0&&i<36);
  for(const e of body) {
    assert.deepEqual(e.r.filter((_,i)=>i%3===0&&i<36),carried);
    const old=Array.from({length:12},(_,j)=>expected[e.slot][1+3*j]);
    for(let j=0;j<12;j++)expected[e.slot][1+3*j]=carried[j];
    carried=old;
  }
  assert.deepEqual(ringAt(r,command+targets.length),expected,'exact E7/A8 output among all 630 tetras');
  const next=r.traced.events.find(e=>e.command===command+targets.length);assert.ok(next);
  assert.deepEqual(next.r.filter((_,i)=>i%3===0&&i<36),carried,'displaced last word survives up to the next command');
  const writes=r.traced.writes.filter(w=>w.command>=command&&w.command<command+targets.length);
  assert.deepEqual(writes.map(w=>[w.chip,w.slot,w.nibble]),targets.flatMap(n=>Array.from({length:12},(_,j)=>[3,n,1+3*j])));
  return {body,after:next};
}

function check(r) {
  assert.deepEqual(r.options.afterQuiet,p.actions({}));
  const prefix=checkPrefix(r),[a,b,c,d]=upper.map(n=>r.before[n].slice(2));
  for(const n of [b,c]) {
    const x=normalization(n);assert.ok(x.cuts+Number(x.small)<=5,'current direct backup needs formatter to return both b and c to X');
  }
  const stores=[store(r,3,b,'W'),store(r,4,c,'Q')];
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>i===2?b:i===3?c:[6,10,14].includes(i)?m:v));
  assert.deepEqual(r.after,{...r.before,U:r.before.U.slice(0,2)+'958912340000',
    V:r.before.V.slice(0,2)+'958912345678',W:r.before.W.slice(0,2)+m,
    Q:r.before.Q.slice(0,2)+'1F'+b[2]+'912345678',
    P8:r.before.P8.slice(0,2)+c,P9:r.before.P9.slice(0,2)+b});
  const begin=r.traced.events.find(e=>e.stage===stage(3));
  assert.ok(r.traced.writes.filter(w=>w.command>=begin.command&&ms.includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value),'neither store changes even a temporary Ms tetra');
  const second=r.traced.events.find(e=>e.stage===stage(4)&&e.ring);assert.ok(second);
  assert.equal(raw(second.ring.X),c,'the first store return, not its D4 source, delivers c to X');
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(r.traced.events.every(e=>e.ip!==0xC9));
  return {phase:r.options.phaseOffset,prefix:prefix.ack,stores,upper:[a,c,b,d],programPreserved:true};
}

if(require.main===module) {
  const cases=[{phaseOffset:2},
    {phaseOffset:0,fullUpper:['-7.654321E23','1.2345678E42','8.7654321E-17','-1E-99']},
    {phaseOffset:1,fullUpper:['1111','-1.23E-42','3333','4444']}];
  const from=Number(process.env.MS_QUIET_UPPER_FROM??0),count=Number(process.env.MS_QUIET_UPPER_CASES??cases.length);
  for(const o of cases.slice(from,from+count)) {const r=p.run(o);console.log('PASS upper pair backup:',JSON.stringify(check(r)));release(r);}
  console.log('LIMIT: a conditional two-word backup using P2/P3, not a full exchange or restored work-register bank.');
}
module.exports={check,checkPrefix,prefixView,store,swap};
