#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_quiet_upper_restore.cjs');
const four=require('./probe_ms_quiet_read_four.cjs');
const {check:checkFour}=require('./check_ms_quiet_read_four.cjs');
const {prefixView,store,swap}=require('./check_ms_quiet_upper.cjs');
const {secondaryBlock}=require('./check_ms_clone_quiet_request.cjs');
const {normalization}=require('./check_ms_clone_numeric_x.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {release}=require('./check_ms_marker_clone_w.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {createHash}=require('node:crypto');
const m='0000F0000000',zero='000000000000';

function recall(r,index,sourceSlot,value) {
  const es=r.traced.events,xs=es.filter(e=>e.stage==='clone-quiet-after-'+index);
  const ds=xs.filter(e=>e.ip===0xD6);assert.equal(ds.length,1);assert.equal(ds[0].slot,sourceSlot);assert.equal(raw(ds[0].m,0),value);
  const first=xs.find(e=>e.ip===0xE7&&e.command>ds[0].command);assert.ok(first);assert.equal(raw(first.r,0),value);
  return swap(r,first.command,['P8','P9','P10','marker']);
}
function check(r,{unsafeD=false}={}) {
  assert.deepEqual(r.options.afterQuiet,four.options(p.options({})).afterQuiet);
  const prefix=prefixView(r,15);checkFour(prefix);
  const [a,b,c,d]=['P7','P8','P9','P10'].map(n=>r.before[n].slice(2));
  const dn=normalization(d),lengthClass=dn.cuts+Number(dn.small);
  assert.ok(unsafeD?lengthClass<4:lengthClass>=4,'the declared d class must match the formatter-control contract');
  const es=r.traced.events,ww=r.traced.writes;
  recall(r,15,'Q',c);store(r,16,c,'P9','P8');
  recall(r,17,'W',b);store(r,18,b,'P10','P8');
  recall(r,19,'P7',a);
  const write=es.filter(e=>e.stage==='clone-quiet-after-20'&&e.ip===0xE9);assert.equal(write.length,1);
  assert.equal(write[0].slot,'P7');assert.equal(raw(write[0].r,0),a);
  const expected=ringAt(r,write[0].command);for(let j=0;j<12;j++)expected.P7[1+3*j]=write[0].r[3*j];
  assert.deepEqual(ringAt(r,write[0].command+1),expected,'single exact a write among all 630 tetras');
  assert.deepEqual(ww.filter(w=>w.command===write[0].command).map(w=>[w.chip,w.slot,w.nibble]),Array.from({length:12},(_,j)=>[3,'P7',1+3*j]));
  const pairAt=es.findIndex(e=>e.stage==='clone-quiet-after-20'&&e.otherChips?.[4].ip===0x4E);
  const pair=secondaryBlock(r,pairAt,[0x4E,0x2A],['P8','P9']);
  assert.equal(raw(pair.after.ring.P8),b);assert.equal(raw(pair.after.ring.P9),a);
  const clear=es.filter(e=>e.stage==='clone-quiet-after-21'&&e.ip===0xE7);assert.equal(clear.length,1);
  assert.equal(raw(clear[0].r,0),zero);swap(r,clear[0].command,['P8']);
  const planted=recall(r,22,'X1',m);
  assert.deepEqual(['P8','P9','P10','marker'].map(n=>raw(ringAt(r,planted.after.command)[n])),[m,zero,a,c]);
  const moved=[];
  for(const [i,source,value,words] of [
    [23,'P8',d,[d,m,zero,a]],[24,'P9',c,[c,d,m,zero]],[25,'P10',b,[b,c,d,m]]]) {
    const block=recall(r,i,source,value);moved.push(block.body[0].command);
    assert.deepEqual(['P8','P9','P10','marker'].map(n=>raw(ringAt(r,block.after.command)[n])),words);
    if(i===23) {
      const form=es.find(e=>e.stage==='clone-quiet-after-23'&&e.ip===0xEE&&e.command>block.after.command);assert.ok(form);
      assert.equal(form.slot,'P8');assert.equal(raw(form.m),d);
      assert.deepEqual([form.s1,form.r[38],form.r[41],form.sp[0]],[13,12,15,0xE3]);
      const ring=ringAt(r,form.command);
      assert.deepEqual(Object.keys(ring).filter(n=>ring[n][22]===15).sort(),['P9','W']);
      const returned=es.find(e=>e.stage===form.stage&&e.ip===0xE7&&e.command>form.command);assert.ok(returned);
      assert.equal(returned.slot,unsafeD?'control':'P8');assert.equal(raw(returned.r,0),d);
      if(unsafeD)assert.equal(raw(returned.m),'1F0000000000');
      swap(r,returned.command,[returned.slot]);
    }
  }
  assert.deepEqual(r.after,{...prefix.after,Q:prefix.after.Q.slice(0,2)+'1F'+a[2]+'912345678',
    ...Object.fromEntries(['P7','P8','P9','P10'].map(n=>[n,r.before[n]]))});
  assert.deepEqual(r.afterRegisters,prefix.afterRegisters.map((v,i)=>i===6?c:i===7?b:v));
  assert.deepEqual([r.afterRegisters[4],r.afterRegisters[2],r.afterRegisters[3],r.afterRegisters[5]],[a,b,c,d]);
  const start=es.find(e=>e.stage==='clone-quiet-after-15');
  assert.ok(ww.filter(w=>w.command>=start.command&&['U','V','W'].includes(w.slot)&&w.nibble%3===1).every(w=>w.before===w.value));
  assert.ok(ww.filter(w=>w.command>write[0].command&&w.slot==='P7'&&w.nibble%3===1).every(w=>w.before===w.value),'a survives every later restoration command');
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);assert.equal(raw(end.ring.marker),m);
  assert.equal(raw(end.ring.control),unsafeD?d:'1F0000000000','control follows the declared positive/negative contract');
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
  return {phase:r.options.phaseOffset,copies:[a,b,c,d],singleA:write[0].command,markerPushes:moved,
    upperRestored:true,originalMarkerRecreated:true,originalControlPreserved:!unsafeD,WStillMarked:true,programPreserved:true};
}
if(require.main===module) {
  const cases=[{phaseOffset:2},
    {phaseOffset:0,fullUpper:['-7.654321E23','1.2345678E42','8.7654321E-17','-1E-99']},
    {phaseOffset:1,fullUpper:['-1E-99','-1.23E-42','3333','4444']}];
  if(process.env.MS_UPPER_RESTORE_NEGATIVE_D) {
    const r=p.run({phaseOffset:2,fullUpper:['1111','2222','3333','1.2345678E42']});
    console.log('PASS negative d formatter/control boundary:',JSON.stringify(check(r,{unsafeD:true})));release(r);
  } else if(process.env.MS_UPPER_RESTORE_UNOBSERVED) {
    const o=cases[0],r=p.run(o);check(r);const expected=JSON.parse(JSON.stringify(r.calc)),result=structuredClone(r.result);release(r);
    const plain=p.prepare(o),actual=p.finish(plain,o);plain.runFrames(3);aligned(plain);
    assert.deepEqual(actual,result);assert.deepEqual(JSON.parse(JSON.stringify(plain)),expected);
    console.log('PASS upper restoration complete observed/unobserved state:',createHash('sha256').update(JSON.stringify(plain)).digest('hex'));
  } else {
    const from=Number(process.env.MS_UPPER_RESTORE_FROM??0),count=Number(process.env.MS_UPPER_RESTORE_CASES??cases.length);
    for(const o of cases.slice(from,from+count)) {const r=p.run(o);console.log('PASS upper read and restoration:',JSON.stringify(check(r)));release(r);}
  }
}
module.exports={check,recall};
