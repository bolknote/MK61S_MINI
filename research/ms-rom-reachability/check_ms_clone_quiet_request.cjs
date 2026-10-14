#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_clone_quiet_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkClones,release}=require('./check_ms_marker_clone_w.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {normalization}=require('./check_ms_clone_numeric_x.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {createHash}=require('node:crypto');
const m='0000F0000000',h='958912340000',g='958912345678',zero='000000000000';
const upper=['P7','P8','P9','P10'];
const cleared=[['F',','],['↔'],['↔']];

function secondaryBlock(r,at,ips,targets) {
  const es=r.traced.events,body=es.slice(at,at+ips.length),after=es[at+ips.length];
  assert.deepEqual(body.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),ips.map((ip,i)=>[ip,targets[i]]));
  assert.equal(after.otherChips[4].ip,0x39);assert.ok(after.ring);
  const expected=ringAt(r,body[0].command);
  for(const e of body) {
    const c=e.otherChips[4],source=c.ip===0x3A?c.st:c.r;
    for(let j=0;j<12;j++)expected[c.slot][1+3*j]=source[3*j];
  }
  assert.deepEqual(after.ring,expected,'complete secondary output: all 630 tetras');
  const writes=r.traced.writes.filter(w=>w.command>=body[0].command&&w.command<after.command);
  assert.equal(writes.length,12*ips.length);assert.ok(writes.every(w=>w.chip===4));
  assert.deepEqual(writes.map(w=>[w.slot,w.nibble]),targets.flatMap(n=>Array.from({length:12},(_,j)=>[n,1+3*j])));
  return {body,after};
}

function check(r) {
  const es=r.traced.events,ww=r.traced.writes,[a,b,c,d]=upper.map(n=>r.before[n].slice(2));
  assert.equal(r.beforeRegisters[2],h);assert.equal(checkClones(r).length,1);
  assert.ok([undefined,3].includes(r.options.neutralAttempts));assert.ok([undefined,1].includes(r.options.gapFrames));
  const ack=r.options.afterQuiet!==undefined;
  if(ack)assert.deepEqual(r.options.afterQuiet,cleared);
  const {cuts,small}=normalization(b);assert.ok(cuts+Number(small)<=5,'current ACK contract excludes destructive formatter boundary');
  const begin=es.find(e=>e.stage==='clone-quiet-0'&&e.ring);assert.ok(begin);
  const rotate=es.find(e=>e.stage==='clone-quiet-after-0'&&e.ring);assert.ok(rotate);
  assert.deepEqual(['X','Y','Z','T','U','V','W','Q'].map(n=>raw(begin.ring[n])),[h,m,m,zero,g,h,m,g]);
  assert.deepEqual(['X','Y','Z','T','U','V','W','Q'].map(n=>raw(rotate.ring[n])),[b,m,'2880F0000000',zero,h,g,m,'288912345678']);
  assert.ok(ww.filter(w=>w.command>=begin.command&&w.command<rotate.command).every(w=>w.chip<4||w.before===w.value));
  const submit=es.filter(e=>e.stage.startsWith('clone-quiet-')&&!e.stage.startsWith('clone-quiet-after')&&e.ip===0xA3&&e.slot==='Q');
  assert.equal(submit.length,1);
  const written=ringAt(r,submit[0].command+1);assert.equal(raw(written.Q),'288912345678');
  const requestWrites=ww.filter(w=>w.command===submit[0].command);
  assert.deepEqual(requestWrites.map(w=>[w.chip,w.slot,w.nibble,w.value]),[[3,'Q',28,8],[3,'Q',31,8],[3,'Q',34,2]]);
  const rotAt=es.findIndex(e=>e.stage==='clone-quiet-after-0'&&e.otherChips[4].ip===0x3A);
  assert.ok(rotAt>=0);const rot=secondaryBlock(r,rotAt,[0x3A,0x3A,0x3A,0x2A],['X','Y','Z','T']);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(rot.after.ring[n])),[g,'2580F0000000',zero,h]);
  const removed=es.find(e=>e.stage===(ack?'clone-quiet-after-1':'done')&&e.ring);assert.ok(removed);
  assert.deepEqual(['X','Y','Z','T','U','V','W','Q'].map(n=>raw(removed.ring[n])),[b,'2580F0000000',zero,h,h,g,m,'288912345678']);
  const quiets=es.filter(e=>e.command>rot.after.command&&e.command<removed.command&&e.otherChips?.[4].ip===0x5E&&e.otherChips[4].slot==='Q');
  assert.ok(quiets.length>0,'the formerly hidden Q request is actually decoded after Z removal');
  for(const e of quiets.slice(0,3)) {
    assert.equal(raw(e.otherChips[4].m),'288912345678');
    const at=es.indexOf(e)-1;
    assert.equal(es[at].otherChips[4].r[29],0);assert.equal(es[at].otherChips[4].m[22],15);
    assert.deepEqual(es.slice(at,at+10).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
      [0x6E,0x5E,0x50,0x52,0x53,0x4F,0x24,0x26,0x39,0x6E]
        .map((ip,i)=>[ip,['W','Q','P7','P8','P9','P10','marker','control','X1','X'][i]]));
    assert.ok(ww.filter(w=>w.command>=es[at].command&&w.command<es[at+9].command).every(w=>w.chip!==4));
  }
  let pair;
  if(ack) {
    const first=es.findIndex(e=>e.stage==='clone-quiet-after-1'&&e.otherChips[4].ip===0x4E);
    secondaryBlock(r,first,[0x4E,0x2A],['X','Y']);
    const second=es.findIndex(e=>e.stage==='clone-quiet-after-2'&&e.otherChips[4].ip===0x4E);
    pair=secondaryBlock(r,second,[0x4E,0x2A],['P8','P9']);
    assert.equal(raw(pair.body[0].otherChips[4].r,0),c);
    assert.equal(raw(pair.body[1].otherChips[4].r,0),b);
    const response=es[second-2].otherChips[4];assert.equal(response.ip,0x27);assert.equal(response.slot,'Q');
    assert.equal(r.after.Q.slice(2),'1F'+b[2]+g.slice(3));
    assert.deepEqual(upper.map(n=>r.after[n].slice(2)),[a,c,b,d]);
  } else for(const n of upper)assert.equal(r.after[n],r.before[n]);
  assert.equal(r.after.W.slice(2),m);assert.equal(r.after.U.slice(2),h);assert.equal(r.after.V.slice(2),g);
  assert.ok(ww.filter(w=>upper.includes(w.slot)&&w.nibble%3===1).every(w=>w.before===w.value||
    (ack&&w.command>=pair.body[0].command&&w.command<pair.after.command&&w.chip===4&&['P8','P9'].includes(w.slot)&&w.nibble<=34)));
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),ack?[b,b,'14'+b[2]+'000000000',h]:[b,'2580F0000000',zero,h]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>[6,10,14].includes(i)?m:v));
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {phase:r.options.phaseOffset,neutralRequest:submit[0].command,removeZ:rot.body[0].command,
    quietDecodes:quiets.length,ack,upper:upper.map(n=>r.after[n].slice(2)),WPreserved:true};
}

if(require.main===module) {
  const cases=[{phaseOffset:2},
    {phaseOffset:2,afterQuiet:cleared},
    {phaseOffset:0,afterQuiet:cleared,fullUpper:['-7.654321E23','1.2345678E42','-1E-99','8.7654321E-17']},
    {phaseOffset:1,afterQuiet:cleared,fullUpper:['1111','-1.23E-42','3333','4444']}];
  if(process.env.MS_QUIET_UNOBSERVED) {
    const o=cases[1],r=p.run(o);check(r);const expected=JSON.parse(JSON.stringify(r.calc)),result=structuredClone(r.result);release(r);
    const plain=p.prepare(o),actual=p.finish(plain,o);plain.runFrames(3);aligned(plain);
    assert.deepEqual(actual,result);assert.deepEqual(JSON.parse(JSON.stringify(plain)),expected);
    console.log('PASS quiet-request complete observed/unobserved state:',createHash('sha256').update(JSON.stringify(plain)).digest('hex'));
  } else {
    const from=Number(process.env.MS_QUIET_FROM??0),count=Number(process.env.MS_QUIET_CASES??cases.length);
    for(const o of cases.slice(from,from+count)) {
      const r=p.run(o);console.log('PASS quiet request:',JSON.stringify(check(r)));release(r);
    }
  }
}
module.exports={check,secondaryBlock};
