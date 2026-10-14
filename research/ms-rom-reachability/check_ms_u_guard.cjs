#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_u_guard.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ordinaryChecks}=require('./check_ms_upper_read4.cjs');
const names=['U','V','W','Q','P7','P8','P9','P10'];
const m1=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
const zero='000000000000',marker='0000F0000000';
function checkGuard(r,{prefix='',next='done',requireZero=true,controlWord='901910000000'}={}) {
  const es=r.traced.events,rows=label=>es.filter(e=>e.stage===label);
  const at=label=>{const e=rows(label).find(e=>e.ring);assert.ok(e,label);return e;};
  const begin=at(prefix+'clear-before'),end=at(next);
  const writes=r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command);
  assert.deepEqual(writes.filter(w=>['W','Q','P7','P8','P9','P10'].includes(w.slot)&&w.nibble%3===1&&w.before!==w.value),[],
    'neither the useful nor the fallback route changes any live W/Q or upper Ms tetra');
  assert.ok(writes.filter(w=>names.includes(w.slot)&&w.nibble%3===1&&w.before!==w.value)
    .every(w=>w.nibble<=34&&['U','V'].includes(w.slot)));
  assert.ok(writes.filter(w=>w.nibble%3===0&&w.nibble<=33&&w.before!==w.value)
    .every(w=>w.slot==='Z'),'only ordinary D is scratch in the preparation');
  for(const n of m1.filter(n=>n!=='Z'))assert.equal(raw(end.ring[n],0),raw(begin.ring[n],0));
  assert.equal(raw(end.ring.Z,0),marker);
  const stages=[...new Set(es.filter(e=>e.stage.startsWith(prefix+'guard-')&&e.stage.endsWith('/shifted-swap')).map(e=>e.stage))];
  assert.equal(stages.length,r.options.guardRounds??r.options.rounds??(r.options.guardU?3:1));
  const entries=[];
  for(const label of stages) {
    const seq=rows(label),start=seq.find(e=>e.ring);
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(start.ring[n])),[zero,zero,marker,controlWord]);
    const ei=seq.findIndex(e=>e.ip===0xE9);assert.ok(ei>0);
    const write=seq[ei],source=seq.slice(0,ei).findLast(e=>e.ip===0xEE);
    const guard=seq.find(e=>e.ip===0x9C);assert.ok(source&&guard);
    const useful=write.slot==='U';assert.ok(useful||write.slot==='X1');
    assert.equal(source.slot,useful?'X':'V');assert.equal(write.nextIp,0xA2);
    assert.equal(source.nextIp,0xA1);assert.equal(guard.nextIp,0x9E);
    assert.equal(guard.slot,useful?'T':'control');
    if(useful){assert.equal(source.raw,zero);assert.equal(guard.raw,controlWord);}
    const path=seq.slice(seq.indexOf(source),ei+2);
    const expected=useful?[[0xEE,'X'],[0xA1,'Y'],[0xE5,'Z'],[0xE6,'T'],[0xE9,'U'],[0xA2,'V']]:
      [[0xEE,'V'],[0xA1,'W'],...['Q','P7','P8','P9','P10','marker'].map(n=>[0xE5,n]),
        [0xE6,'control'],[0xE9,'X1'],[0xA2,'X']];
    assert.deepEqual(path.map(e=>[e.ip,e.slot]),expected);
    assert.ok(path.every((e,i)=>e.command===source.command+i));
    assert.equal(raw(write.r,0),source.raw);
    const out=structuredClone(write.ring);
    for(let j=0;j<12;j++)out[write.slot][1+3*j]=source.m[1+3*j];
    assert.deepEqual(seq[ei+1].ring,out,'all 630 tetras: E9 replaces exactly one numeric word');
    const ww=writes.filter(w=>w.command===write.command);
    assert.equal(ww.length,12);assert.ok(ww.every(w=>w.chip===3&&w.slot===write.slot&&w.nibble%3===1&&w.nibble<=34));
    const request=seq.find(e=>e.ip===0xA3);assert.ok(request);assert.equal(request.slot,useful?'control':'T');
    entries.push({stage:label,slot:write.slot,command:write.command,request:request.slot});
  }
  const cleared=entries.filter(e=>e.slot==='U');
  assert.ok(writes.filter(w=>w.slot==='U'&&w.nibble%3===1&&w.before!==w.value)
    .every(w=>w.value===0&&w.chip===3&&w.ip===0xE9&&cleared.some(e=>e.command===w.command)),
    'U can only be replaced by zero at the checked E9 commands, never dirtied again');
  if(requireZero){assert.ok(cleared.length>0,'at least one attempt must actually execute E9(U)');assert.equal(raw(end.ring.U),zero);}
  for(const n of ['W','Q','P7','P8','P9','P10'])assert.equal(raw(end.ring[n],1,14),raw(begin.ring[n],1,14));
  for(const n of ['X','Y','Z','T'])assert.equal(raw(end.ring[n]),zero);
  return entries;
}
function check(r,o={}) {
  const entries=checkGuard(r,o);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters.map((v,i)=>i===13?marker:v));
  ordinaryChecks(r);return entries;
}
function checkMiss(r) {
  const entries=check(r,{requireZero:false});
  assert.ok(entries.every(e=>e.slot==='X1'));
  assert.equal(r.after.U,r.before.U);assert.notEqual(r.after.U.slice(2),zero);
  return entries;
}
function negatives() {
  for(const o of [{phaseOffset:2,rounds:1},
    {phaseOffset:0,rounds:3,settleFrames:12,markerFrames:8,phaseSweep:false}]) {
    const r=p.run(o);console.log('PASS rejected incomplete phase coverage:',JSON.stringify(o),JSON.stringify(checkMiss(r)));
    r.traced.events.length=0;r.traced.writes.length=0;
  }
  const fixed=p.run({phaseOffset:0,rounds:3,settleFrames:12,markerFrames:8});
  console.log('PASS corrected phase coverage:',JSON.stringify(check(fixed)));
  fixed.traced.events.length=0;fixed.traced.writes.length=0;
}
if(require.main===module) {
  if(process.env.MS_U_GUARD_NEGATIVE_ONLY==='1')negatives();
  else {
    const r=p.run(process.argv[2]?JSON.parse(process.argv[2]):{rounds:3});
    console.log('PASS U preparation:',JSON.stringify(check(r)));
  }
}
module.exports={checkGuard,check,checkMiss,negatives};
