#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_quiet_read_four.cjs');
const {check:checkFifth}=require('./check_ms_quiet_fifth_zero.cjs');
const {prefixView,store,swap}=require('./check_ms_quiet_upper.cjs');
const {secondaryBlock}=require('./check_ms_clone_quiet_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {release}=require('./check_ms_marker_clone_w.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {createHash}=require('node:crypto');
const zero='000000000000';
function check(r) {
  assert.deepEqual(r.options.afterQuiet,p.options({}).afterQuiet);
  const prefix=prefixView(r,10);checkFifth(prefix);
  const [a,b,c,d]=['P7','P8','P9','P10'].map(n=>r.before[n].slice(2)),e=r.beforeRegisters[0];
  const es=r.traced.events,push=es.find(x=>x.stage==='clone-quiet-after-10'&&x.ip===0xE7);assert.ok(push);
  assert.equal(raw(push.r,0),e);
  const first=swap(r,push.command,['P8','P9','P10','marker']);
  assert.deepEqual(['P8','P9','P10','marker'].map(n=>raw(ringAt(r,first.after.command)[n])),[e,zero,b,d]);
  const rotations=[];
  for(let i=0;i<3;i++) {
    const stage='clone-quiet-after-'+(11+i),xs=es.filter(x=>x.stage===stage),source=[e,zero,b][i];
    const copy=xs.filter(x=>x.ip===0xE9);assert.equal(copy.length,1);assert.equal(copy[0].slot,'P7');assert.equal(raw(copy[0].r,0),source);
    const before=ringAt(r,copy[0].command),after=ringAt(r,copy[0].command+1);
    for(let j=0;j<12;j++)before.P7[1+3*j]=copy[0].r[3*j];assert.deepEqual(after,before);
    assert.deepEqual(r.traced.writes.filter(w=>w.command===copy[0].command).map(w=>[w.chip,w.slot,w.nibble]),
      Array.from({length:12},(_,j)=>[3,'P7',1+3*j]));
    const at=es.findIndex(x=>x.stage===stage&&x.otherChips?.[4].ip===0x3A);
    assert.ok(at>=0);const block=secondaryBlock(r,at,[0x3A,0x3A,0x3A,0x2A],['P8','P9','P10','marker']);
    const expected=[[zero,b,d,e],[b,d,e,zero],[d,e,zero,b]][i];
    assert.deepEqual(['P8','P9','P10','marker'].map(n=>raw(block.after.ring[n])),expected);
    rotations.push(block.body[0].command);
  }
  const saved=store(r,14,d,'P8','P8');
  assert.deepEqual(r.afterRegisters,prefix.afterRegisters.map((v,i)=>i===5?d:v));
  assert.deepEqual([r.afterRegisters[4],r.afterRegisters[2],r.afterRegisters[3],r.afterRegisters[5]],[a,b,c,d]);
  assert.deepEqual(r.after,{...prefix.after,Q:prefix.after.Q.slice(0,2)+'2F'+b[2]+'912345678',
    P7:prefix.after.P7.slice(0,2)+b,P8:prefix.after.P8.slice(0,2)+d,
    P9:prefix.after.P9.slice(0,2)+e,P10:prefix.after.P10.slice(0,2)+zero});
  const begin=es.find(x=>x.stage==='clone-quiet-after-10');
  assert.ok(r.traced.writes.filter(w=>w.command>=begin.command&&['U','V','W'].includes(w.slot)&&w.nibble%3===1).every(w=>w.before===w.value));
  assert.ok(r.traced.writes.filter(w=>w.command>=begin.command&&['U','V','W','Q','P7','P8','P9','P10'].includes(w.slot)&&[37,40].includes(w.nibble))
    .every(w=>w.before===w.value),'all Ms service fields held');
  const end=es.find(x=>x.stage==='done'&&x.ring);assert.ok(end);
  assert.equal(raw(end.ring.marker),b,'original marker is deliberately replaced by a numeric word');
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(end.ring[n])),[a,c,b,'14'+b[2]+'000000000']);
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(x=>x.ip!==0xC9));
  return {phase:r.options.phaseOffset,upperCopies:[a,b,c,d],push:first.body[0].command,rotations,store:saved,
    originalMarkerRestored:false,programPreserved:true};
}
if(require.main===module) {
  const cases=[{phaseOffset:2},
    {phaseOffset:0,fullUpper:['-7.654321E23','1.2345678E42','8.7654321E-17','-1E-99']},
    {phaseOffset:1,fullUpper:['-1E-99','-1.23E-42','3333','4444']}];
  if(process.env.MS_QUIET_FOUR_UNOBSERVED) {
    const o=cases[0],r=p.run(o);check(r);const expected=JSON.parse(JSON.stringify(r.calc)),result=structuredClone(r.result);release(r);
    const plain=p.prepare(o),actual=p.finish(plain,o);plain.runFrames(3);aligned(plain);
    assert.deepEqual(actual,result);assert.deepEqual(JSON.parse(JSON.stringify(plain)),expected);
    console.log('PASS four copies complete observed/unobserved state:',createHash('sha256').update(JSON.stringify(plain)).digest('hex'));
  } else {
    const from=Number(process.env.MS_QUIET_FOUR_FROM??0),count=Number(process.env.MS_QUIET_FOUR_CASES??cases.length);
    for(const o of cases.slice(from,from+count)) {const r=p.run(o);console.log('PASS all four upper copies:',JSON.stringify(check(r)));release(r);}
  }
  console.log('LIMIT: original marker is replaced; no normal exit, upper restoration, or full K1 is claimed.');
}
module.exports={check};
