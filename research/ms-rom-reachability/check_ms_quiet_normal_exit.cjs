#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_quiet_normal_exit.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {swap}=require('./check_ms_quiet_upper.cjs');
const {normalization}=require('./check_ms_clone_numeric_x.cjs');
const upper=['P7','P8','P9','P10'],zero='000000000000',m='0000F0000000';
const stage=i=>'clone-quiet-after-'+i;
function check(r) {
  assert.ok(r.options.stageB);assert.deepEqual(r.options.cleanupTail.slice(0,6),p.tail);
  const s=i=>stage(i+(r.options.zeroBeforeMarker&&i>=33?1:0));
  const es=r.traced.events,ww=r.traced.writes,[a,b,c,d]=upper.map(n=>r.before[n].slice(2));
  const q=n=>{const f=normalization(n);return f.cuts+Number(f.small);};
  assert.equal(q(b),5);assert.ok(q(c)<=5);assert.ok(q(d)>=4&&q(d)<=5);
  const at=i=>{const e=es.find(e=>e.stage===s(i)&&e.ring);assert.ok(e);return e;};
  const start=at(32);
  for(const n of upper)assert.equal(raw(start.ring[n],1,14),r.before[n]);
  if(r.options.zeroBeforeMarker) {
    const xs=es.filter(e=>e.stage===stage(33)),ds=xs.filter(e=>e.ip===0xD6);assert.equal(ds.length,1);
    assert.equal(ds[0].slot,'Q');assert.equal(raw(ds[0].m,0),zero);
    const first=xs.find(e=>e.ip===0xE7&&e.command>ds[0].command);assert.ok(first);
    assert.equal(raw(first.r,0),zero);swap(r,first.command,['X','Y','Z','T']);
    const zeroReturn=xs.find(e=>e.ip===0xE7&&e.command>first.command);assert.ok(zeroReturn);
    assert.equal(zeroReturn.slot,'P8');assert.equal(raw(zeroReturn.r,0),zero);
    assert.equal(zeroReturn.nextIp,0x47);swap(r,zeroReturn.command,['P8']);
    assert.equal(raw(at(33).ring.X),zero);
    assert.equal(raw(at(34).ring.Y),zero,'false control after visible X marker is explicitly zero');
    assert.ok(es.filter(e=>e.stage===s(34)&&e.ip===0x9C&&e.slot==='Y').every(e=>e.nextIp!==0x9E));
  }
  for(const [i,destination,value] of [[32,'P8',zero],[35,'P8',zero]]) {
    const ee=es.filter(e=>e.stage===s(i)&&e.ip===0xE7);assert.equal(ee.length,1);
    assert.equal(ee[0].slot,destination);assert.equal(raw(ee[0].r,0),value);swap(r,ee[0].command,[destination]);
  }
  const transfers=[];
  for(const [i,source,value] of [[33,'W',m],[34,'P8',d],[36,'P7',b],[37,'P8',d],[38,'U',a]]) {
    const xs=es.filter(e=>e.stage===s(i)),ds=xs.filter(e=>e.ip===0xD6);assert.equal(ds.length,1);
    assert.equal(ds[0].slot,source);assert.equal(raw(ds[0].m,0),value);
    const first=xs.find(e=>e.ip===0xE7&&e.command>ds[0].command);assert.ok(first);
    assert.equal(raw(first.r,0),value);swap(r,first.command,['X','Y','Z','T']);
    if(i===36||i===37) {
      const form=xs.find(e=>e.ip===0xEE&&e.command>first.command);assert.ok(form);
      assert.equal(form.slot,'X');assert.equal(raw(form.m),value);
      assert.deepEqual([form.s1,form.r[38],form.r[41],form.sp[0]],[13,12,15,0xE3]);
      assert.deepEqual(Object.entries(ringAt(r,form.command)).filter(([,word])=>word[22]===15).map(([n])=>n).sort(),
        ['marker','W',i===36?'Z':'T'].sort());
      const write=xs.find(e=>e.ip===0xE7&&e.command>form.command);assert.ok(write);
      assert.equal(write.slot,i===36?'P8':'W');assert.equal(raw(write.r,0),value);
      assert.equal(write.nextIp,0x47);swap(r,write.command,[write.slot]);
      transfers.push({stage:i,source:form.command,write:write.command,target:write.slot,value});
    }
  }
  const normal=at(39);
  assert.deepEqual(Object.entries(normal.ring).filter(([,word])=>word[22]===15).map(([n])=>n),['marker']);
  assert.equal(raw(normal.ring.control),'1F0000000000');
  const end=es.find(e=>e.stage==='done'&&e.ring);assert.ok(end);
  assert.deepEqual(Object.entries(end.ring).filter(([,word])=>word[22]===15).map(([n])=>n),['marker']);
  const afterClear=r.options.verifyExit?at(40):end;
  for(const n of ['X','Y','Z','T'])assert.equal(raw(afterClear.ring[n]),zero);
  assert.deepEqual(r.after,{...r.before,U:r.before.U.slice(0,2)+'958912340000',V:r.before.V.slice(0,2)+'958912345678',
    W:r.before.W.slice(0,2)+d,Q:r.before.Q.slice(0,2)+'1F'+a[2]+'912345678'});
  assert.deepEqual([r.afterRegisters[0],r.afterRegisters[4],r.afterRegisters[6],r.afterRegisters[5]],[a,b,c,d]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>
    ({0:a,2:m,3:zero,4:b,5:d,6:c,7:b,10:m,14:m})[i]??v));
  // The normal program runner temporarily rewrites/restores its current
  // program page with C9. The no-transient-writes claim is for our cleanup,
  // not for the emulator's ordinary execution mechanism tested afterwards.
  const cleanupEnd=r.options.verifyExit?at(40).command:Infinity;
  const writes=ww.filter(w=>w.command>=start.command&&w.command<cleanupEnd);
  assert.ok(writes.filter(w=>w.nibble%3===0||w.nibble%3===2||w.nibble>=37).every(w=>w.before===w.value),
    'cleanup preserves M1, program lane and service tetras even transiently');
  for(const n of ['P7','P9','P10'])assert.ok(writes.filter(w=>w.slot===n).every(w=>w.before===w.value));
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  if(r.options.verifyExit) {
    assert.equal(raw(at(41).ring.X),'000050000000','ordinary 2 ENTER 3 + = 5');
    assert.equal(raw(at(42).ring.X),zero,'a distinct zero sentinel before running the saved program');
    assert.equal(raw(end.ring.X),'000050000000','the unchanged saved program also produces 5');
    assert.deepEqual(r.beforeProgram.slice(0,5),[2,14,3,16,80]);
  }
  return {phase:r.options.phaseOffset,upperRestored:true,copies:[a,b,c,d],transfers,
    allExtraMarkersRemoved:true,programHeld:true,ordinaryAndProgramChecks:!!r.options.verifyExit};
}
if(require.main===module) {
  const cases=[{phaseOffset:2},{phaseOffset:0,verifyExit:true},{phaseOffset:1,verifyExit:true},
    {phaseOffset:1,verifyExit:true,fullUpper:['-1E-99','-1.23E-42','3333','-1.234E-42']}];
  const from=Number(process.env.MS_NORMAL_EXIT_FROM??0),count=Number(process.env.MS_NORMAL_EXIT_CASES??cases.length);
  for(const o of cases.slice(from,from+count)) {const r=p.run(o);console.log('PASS normal upper exit:',JSON.stringify(check(r)));
    r.traced.events.length=r.traced.writes.length=0;}
  console.log('LIMIT: numeric classes and scratch inputs remain; this is upper read/restore, not full K1.');
}
module.exports={check};
