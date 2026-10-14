#!/usr/bin/env node
'use strict';
// Negative continuation: the first read masks a request at Q; a second
// key 25 exposes it and destroys W. It is not a successful W cleanup.
const assert=require('node:assert/strict');
const p=require('./probe_ms_clone_load_x.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkClones,release}=require('./check_ms_marker_clone_w.cjs');
const m='0000F0000000',h='958912340000',zero='000000000000';
const upper=['P7','P8','P9','P10'];

function ringAt(r,command) {
  const start=r.traced.events.findLast(e=>e.command<=command&&e.ring);assert.ok(start);
  const ring=structuredClone(start.ring);
  for(const w of r.traced.writes.filter(w=>w.command>=start.command&&w.command<command)) {
    assert.equal(ring[w.slot][w.nibble],w.before,'passive write-log predecessor');
    ring[w.slot][w.nibble]=w.value;
  }
  const exact=r.traced.events.find(e=>e.command===command&&e.ring);
  if(exact)assert.deepEqual(ring,exact.ring);
  return ring;
}

function check(r) {
  assert.equal(r.options.phaseOffset,2);assert.equal(r.beforeRegisters[2],h);
  assert.deepEqual(r.options.tailActions,[['F',','],['F',',']]);
  assert.equal(r.options.tailLeadFrames,undefined);assert.equal(checkClones(r).length,1);
  const es=r.traced.events,ww=r.traced.writes;
  const [a,b]=upper.map(n=>r.before[n].slice(2));
  const next=es.find(e=>e.stage==='clone-load-tail-1'&&e.ring);assert.ok(next);
  assert.deepEqual(['X','Y','Z','T','U','V','W','Q'].map(n=>raw(next.ring[n])),
    [b,m,m,zero,h,h,m,'258912345678']);
  for(const n of upper)assert.equal(raw(next.ring[n]),r.before[n].slice(2));
  const submitted=es.find(e=>e.stage==='clone-load-tail-0'&&e.ip===0xA3&&e.slot==='Q');assert.ok(submitted);
  const stop=es.findLast(e=>e.stage==='clone-load-tail-0'&&e.ip===0x47);assert.ok(stop);
  const quiet=es.filter(e=>e.stage==='clone-load-tail-0'&&e.command>stop.command);
  const seq=[0x6E,0x5E,0x39,0x6E,0x6E,0x5E,0x50,0x52,0x53,0x4F,0x24,0x39,0x6E,0x6E,0x6E];
  const names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  let laps=0;
  for(let i=0;i+15<quiet.length;i++) {
    const c=quiet[i].otherChips[4];if(c.ip!==0x6E||c.slot!=='marker')continue;
    const lap=quiet.slice(i,i+16),chips=lap.map(e=>e.otherChips[4]);
    assert.deepEqual(chips.map(c=>[c.ip,c.slot]),[...seq,0x6E].map((ip,j)=>[ip,names[j%15]]));
    assert.equal(c.r[29],0);assert.equal(chips[15].r[29],0);
    assert.equal(c.m[22],15);assert.deepEqual([chips[1].m[34],chips[1].m[31]],[1,15]);
    assert.equal(chips[4].m[22],15);assert.deepEqual([chips[5].m[34],chips[5].m[31]],[0,0]);
    for(const j of [3,12,13,14])assert.notEqual(chips[j].m[22],15);
    assert.ok(lap.every((e,j)=>e.command===lap[0].command+j));laps++;
  }
  assert.ok(laps>300);assert.ok(ww.filter(w=>w.command>stop.command&&w.command<next.command).every(w=>w.chip!==4));
  const request=es.findIndex(e=>e.stage==='clone-load-tail-1'&&e.otherChips[4].ip===0x5E&&e.otherChips[4].slot==='Q');
  assert.ok(request>=0);assert.equal(raw(es[request].otherChips[4].m),'258912345678');
  assert.ok(ww.filter(w=>w.command>submitted.command&&w.command<es[request].command&&w.slot==='Q'&&w.nibble%3===1)
    .every(w=>w.before===w.value),'the decoded Q request is the old one, not a new write');
  const route='6E 5E 50 52 53 4F 24 26 28 D3 37 27 D4 D4 D4 D4 D4 C4 2C 3B 2B 60 37 37 37 37 27 61 3A 3A 3A 2A 39'
    .split(' ').map(x=>parseInt(x,16));
  assert.deepEqual(es.slice(request-1,request-1+route.length).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    route.map((ip,j)=>[ip,names[(9+j)%15]]));
  const starts=es.filter(e=>e.stage==='clone-load-tail-1'&&e.otherChips[4].ip===0x3A)
    .filter(e=>es[es.indexOf(e)-1].otherChips[4].ip!==0x3A);
  assert.equal(starts.length,3);
  const blocks=[];
  for(const first of starts) {
    const at=es.indexOf(first),body=es.slice(at,at+4),after=es[at+4];
    assert.deepEqual(body.map(e=>e.otherChips[4].ip),[0x3A,0x3A,0x3A,0x2A]);
    assert.equal(after.otherChips[4].ip,0x39);assert.ok(after.ring);
    const expected=ringAt(r,first.command),sources=[];
    for(const e of body) {
      const c=e.otherChips[4],source=c.ip===0x3A?c.st:c.r;sources.push(raw(source,0));
      for(let j=0;j<12;j++)expected[c.slot][1+3*j]=source[3*j];
    }
    assert.deepEqual(after.ring,expected,'secondary four-word output, all 630 tetras');
    const writes=ww.filter(w=>w.command>=first.command&&w.command<after.command);
    assert.equal(writes.length,48);assert.ok(writes.every(w=>w.chip===4));
    assert.deepEqual(writes.map(w=>[w.slot,w.nibble]),body.flatMap(e=>Array.from({length:12},(_,j)=>[e.otherChips[4].slot,1+3*j])));
    blocks.push({command:first.command,slots:body.map(e=>e.otherChips[4].slot),sources});
  }
  assert.deepEqual(blocks.map(x=>x.slots),[['X','Y','Z','T'],['U','V','W','Q'],['U','V','W','Q']]);
  assert.deepEqual(['U','V','W','Q'].map(n=>r.after[n].slice(2)),[b,'258912345678',b,a]);
  for(const n of upper)assert.equal(r.after[n],r.before[n]);
  assert.ok(ww.filter(w=>upper.includes(w.slot)&&w.nibble%3===1).every(w=>w.before===w.value));
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>[6,10,14].includes(i)?m:v));
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {maskedLaps:laps,submitted:submitted.command,decoded:es[request].command,blocks,upperPreserved:true,WPreserved:false};
}
if(require.main===module) {
  const r=p.run({phaseOffset:2,sourceValue:'-1.234E-42',tailActions:[['F',','],['F',',']]});
  console.log('PASS negative delayed-request control:',JSON.stringify(check(r)));release(r);
}
module.exports={check,ringAt};
