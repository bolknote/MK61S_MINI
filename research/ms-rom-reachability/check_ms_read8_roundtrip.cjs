#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_read8_roundtrip.cjs');
const oldRead=require('./check_ms_upper_read4.cjs');
const {checkRotation}=require('./check_ms_upper_write.cjs');
const {compactPath}=require('./check_ms_read6_exit.cjs');
const {checkLowerPush}=require('./check_ms_read6_roundtrip.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {checkQRead}=require('./check_ms_upper_roundtrip.cjs');
const {checkStage:checkWriter}=require('./check_ms_writer_single_pointer.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const names=['U','V','W','Q','P7','P8','P9','P10'],upper=names.slice(4);
const regSlots=[...names,'marker','control','X1','X','Y','Z','T'];
const zero='000000000000',guard='958912345678',marker='0000F0000000';
const rows=(r,label)=>r.traced.events.filter(e=>e.stage===label);
const at=(r,label)=>{const e=rows(r,label).find(e=>e.ring);assert.ok(e,label);return e;};
const ms=ring=>Object.fromEntries(names.map(n=>[n,raw(ring[n],1,14)]));
function held(r,from,to,indices) {
  const start=at(r,from).command,end=at(r,to).command,slots=indices.map(i=>regSlots[i]);
  assert.ok(r.traced.writes.filter(w=>w.command>=start&&w.command<end&&slots.includes(w.slot)&&w.nibble%3===0&&w.nibble<=33)
    .every(w=>w.before===w.value),'retained ordinary words '+indices+' across '+from+'..'+to);
}
function upperUntouched(r,from,to) {
  const start=at(r,from),end=at(r,to);
  assert.deepEqual(upper.map(n=>raw(end.ring[n],1,14)),upper.map(n=>raw(start.ring[n],1,14)));
  assert.ok(r.traced.writes.filter(w=>w.command>=start.command&&w.command<end.command&&upper.includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.before===w.value));
}
function checkLowerBackup(r) {
  if(!r.options.legacyLowerReturn)checkQRead(r,'backup-four/',r.before.Q.slice(2),'backup-four/save-q-to-p6');
  const start=at(r,'backup-four/exchange-wq/clear-before'),saved=at(r,'backup-four/source-p7'),end=at(r,'relocate-6-/-/');
  assert.deepEqual(ms(start.ring),r.before);assert.deepEqual(ms(end.ring),r.before);
  for(const [index,n] of [[4,'U'],[5,'V'],[6,'W'],[7,'Q']]) {
    assert.equal(raw(saved.ring[regSlots[index]],0),r.before[n].slice(2));
    assert.equal(raw(end.ring[regSlots[index]],0),r.before[n].slice(2));
    checkLowerPush(r,'backup-four/write-p'+index+'/',r.before[n].slice(2));
  }
  const changed=r.traced.writes.filter(w=>w.command<end.command&&names.includes(w.slot)&&w.nibble%3===1&&w.value!==w.before);
  assert.ok(changed.every(w=>w.command>=start.command&&names.slice(0,4).includes(w.slot)&&w.nibble<=34));
  const relocated=at(r,'initial-zero-source').ring;
  for(const [index,n] of [[1,'U'],[6,'V'],[11,'W'],[13,'Q']])assert.equal(raw(relocated[regSlots[index]],0),r.before[n].slice(2));
}
function checkMarkerCarrier(r,prefix,next) {
  const begin=at(r,prefix+'save-e-in-p9'),stored=at(r,prefix+'compact-payload-marker'),end=at(r,next),payload=raw(begin.ring.T,0);
  assert.equal(raw(stored.ring.control,0),payload);
  const es=r.traced.events,di=es.findIndex(e=>e.stage===prefix+'plant-u'&&e.ip===0xD6);assert.ok(di>=0);
  assert.equal(es[di].slot,'X1');assert.equal(raw(es[di].m,0),marker);
  const seq=[[0xD6,'X1'],[0xA7,'X'],[0xE5,'Y'],[0xE6,'Z'],[0xE8,'T'],[0xE7,'U'],
    [0xA8,'V'],[0xA8,'W'],[0xA8,'Q'],[0xA9,'P7'],[0xAC,'P8']];
  assert.deepEqual(es.slice(di,di+seq.length).map(e=>[e.ip,e.slot]),seq,'A carries the marker into U through the exact shorter E5 suffix');
  const block=checkSwapBlock(r,di+5,4);assert.equal(raw(block.body[0].r,0),marker);
  assert.equal(raw(block.after.ring.U),marker);
  held(r,prefix+'compact-payload-marker',next,[9]);
  assert.equal(raw(end.ring.T,0),payload,'E is restored after its real pointer use');
}
function checkReader(r) {
  assert.ok(!r.options.unsafeSpareE);
  checkLowerBackup(r);checkLowerPush(r,'initial-zero-u/',zero);
  const [a,b,c,d]=upper.map(n=>r.before[n].slice(2)),paths=[],ends=['park-a-source','save-c-in-e','read-final-a/exchange-wq/clear-before'];
  for(let i=0;i<3;i++) {
    const prefix='read-'+i+'/',begin=at(r,prefix+'prepare-zero-p8'),end=at(r,ends[i]);
    assert.equal(raw(begin.ring.U),zero,'known U cleanup before each reader entry');
    assert.deepEqual(upper.slice(1).map(n=>raw(begin.ring[n])),[[b,c,d],[c,d,guard],[d,guard,guard]][i]);
    checkMarkerCarrier(r,prefix,ends[i]);
    const seed=checkSwapBlock(r,r.traced.events.findIndex(e=>e.stage===prefix+'shift-0'&&e.ip===0xE7&&e.slot==='U'),4);
    assert.equal(raw(seed.body[0].r,0),i?b:zero);assert.equal(raw(seed.after.ring.V),marker);
    if(i===0)oldRead.checkCopy(r,prefix+'upper-copy-fifth',a,'marker');
    const prime=checkSwapBlock(r,r.traced.events.findIndex(e=>e.stage===prefix+'upper-prime'&&e.ip===0xE7&&e.slot==='P7'),1);
    assert.equal(raw(prime.body[0].r,0),guard);
    const rotation=checkRotation(r,prefix+'upper-swap');
    const capture=compactPath(r.traced.events,prefix+'upper-after-0',{capture:true});
    oldRead.checkCopy(r,prefix+'upper-after-0',[b,c,d][i],'X1');
    const post=oldRead.checkExit(r,prefix,{postPointer:Number(r.options.postPointer??110)});
    const markerEntry=rows(r,prefix+'upper-after-4').find(e=>e.ip===0xD6).slot;
    paths.push({capture:capture.start,post:post.start,marker:markerEntry});
    assert.deepEqual(upper.slice(1).map(n=>raw(end.ring[n])),[[c,d,guard],[d,guard,guard],[guard,guard,guard]][i]);
    assert.ok([guard,zero,[b,c,d][i]].includes(raw(end.ring.P7)));
    assert.ok(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&upper.slice(1).includes(w.slot)&&w.nibble%3===1&&w.value!==w.before)
      .every(w=>w.command>=rotation.start&&w.command<rotation.end));
    if(i)assert.equal(raw(end.ring.Q),a,'a survived this reader in lower Q');
  }
  checkLowerPush(r,'park-a/to-u/',a);checkLowerPush(r,'park-a/to-v/',zero);
  assert.equal(raw(at(r,'read-1/save-e-in-p9').ring.V),a);
  assert.equal(raw(at(r,'read-2/save-e-in-p9').ring.V),a);
  if(Number(r.options.postPointer??110)===110) {
    for(const prefix of ['bridge-reader-a/','read-final-a/']) {
      const u=raw(at(r,prefix+'exchange-wq/clear-before').ring.U);
      assert.ok([zero,b].includes(u),'late zero-source exit must not leave the negative guard in U');
      assert.notEqual(u[0],'9','the Q-reader entry domain requires a nonnegative exponent here');
    }
  }
  const overlaps=[checkQRead(r,'bridge-reader-a/',a,'bridge-reader-a/to-u/clear-before'),
    checkQRead(r,'read-final-a/',a,'save-a-in-c')];
  checkLowerPush(r,'bridge-reader-a/to-u/',a);checkLowerPush(r,'bridge-reader-a/to-v/',zero);
  const handoff=r.options.readOnly?'final-zero-source':'lower-v-to-p3',ring=at(r,handoff).ring;
  const outputs=[1,6,11,13,12,8,14,10];
  outputs.forEach((index,i)=>assert.equal(raw(ring[regSlots[index]],0),r.before[names[i]].slice(2),'all eight simultaneous readouts'));
  held(r,'initial-zero-source',handoff,[1,6,11,13]);held(r,'read-1/save-e-in-p9',handoff,[8]);
  upperUntouched(r,'bridge-reader-a/exchange-wq/clear-before','read-2/save-e-in-p9');
  upperUntouched(r,'read-final-a/exchange-wq/clear-before',handoff);
  return {paths,overlaps};
}
function checkBufferBridge(r,prefix,next,source) {
  const begin=at(r,prefix+'save-p3-in-p7'),end=at(r,next),v=r.before.V.slice(2);
  assert.equal(raw(begin.ring.Q),source);assert.equal(raw(begin.ring.Q,0),v);
  const overlap=checkQRead(r,prefix,source,prefix+'to-u/clear-before');
  assert.equal(raw(at(r,prefix+'to-u/clear-before').ring.P10,0),v);
  checkLowerPush(r,prefix+'to-u/',source);checkLowerPush(r,prefix+'to-v/',zero);
  assert.equal(raw(end.ring.V),source);assert.equal(raw(end.ring.U),zero);assert.equal(raw(end.ring.Q,0),v);
  held(r,prefix+'save-p3-in-p7',next,[1,8,10,11,13,14]);upperUntouched(r,prefix+'save-p3-in-p7',next);return overlap;
}
function check(r) {
  const read=checkReader(r),[u,v,w,q,a,b,c,d]=names.map(n=>r.before[n].slice(2));
  if(r.options.readOnly) {
    for(let i=0;i<4;i++)checkLowerPush(r,'clear-lower-'+i+'/',zero);
    assert.deepEqual(names.slice(0,4).map(n=>r.after[n].slice(2)),Array(4).fill(zero));
    const last=read.paths[2];
    const late=Number(r.options.postPointer??110);
    assert.deepEqual(r.afterRegisters,['0020'+late+'00000',u,marker,zero,guard,
      last.post==='U'?'007'+String(late).padStart(9,'0'):'007000000010',v,last.marker==='P10'?'007000000009':'000090000000',b,zero,d,w,a,q,c]);
    oldRead.ordinaryChecks(r);return {read};
  }
  checkLowerPush(r,'park-writer-a/to-u/',a);checkLowerPush(r,'park-writer-a/to-v/',zero);
  const opts={keepP8:true,keepE:true},writes=[];
  writes.push(checkWriter(r,'write-d/','bridge-after-d/save-p3-in-p7',d,10,opts));
  const overlaps=[checkBufferBridge(r,'bridge-after-d/','write-c/zero-p0',a)];
  writes.push(checkWriter(r,'write-c/','bridge-after-c/save-p3-in-p7',c,14,opts));
  overlaps.push(checkBufferBridge(r,'bridge-after-c/','write-b/zero-p0',a));
  writes.push(checkWriter(r,'write-b/','exchange-buffer/save-p3-in-p7',b,8,opts));
  overlaps.push(checkQRead(r,'exchange-buffer/',a,'exchange-buffer/a-to-c'));
  checkLowerPush(r,'exchange-buffer/to-u/',d);checkLowerPush(r,'exchange-buffer/to-v/',zero);
  const last=at(r,'write-a/zero-p0').ring;
  assert.equal(raw(last.X1,0),a);assert.equal(raw(last.V),d);assert.equal(raw(last.Q,0),v);
  upperUntouched(r,'exchange-buffer/save-p3-in-p7','write-a/zero-p0');held(r,'exchange-buffer/save-p3-in-p7','write-a/zero-p0',[1,8,11,13,14]);
  writes.push(checkWriter(r,'write-a/','restore-all/save-p3-in-p7',a,10,opts));
  assert.deepEqual(upper.map(n=>raw(at(r,'restore-all/save-p3-in-p7').ring[n])),[a,b,c,d]);
  overlaps.push(checkQRead(r,'restore-all/',d,'restore-all/d-to-p6'));
  for(const [key,source] of [['Сx',q],['/-/',w],['5',v],['1',u]])checkLowerPush(r,'restore-lower-'+key+'/',source);
  upperUntouched(r,'restore-all/save-p3-in-p7','done');
  assert.deepEqual(r.after,r.before,'all eight complete 14-tetra Ms words restored');
  assert.deepEqual(r.afterRegisters,[zero,u,marker,zero,guard,v,d,v,b,u,a,w,'007000000000',q,c]);
  held(r,'initial-zero-source','done',[1,11,13]);held(r,'read-1/save-e-in-p9','done',[8]);
  held(r,'lower-v-to-p3','done',[14]);
  oldRead.ordinaryChecks(r);return {read,writes,overlaps};
}
const complex={stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
  fullUpper:['3.2109876E-19','-4.3210987E31','1.2345678E-42','-9.8765432E17']};
const cases=[{}, {...complex,phaseOffset:1}, {...complex,phaseOffset:2},
  {...complex,fullUpper:['0','0','0','0']}, {...complex,settleFrames:12,markerFrames:8}];
function release(r){r.traced.events.length=0;r.traced.writes.length=0;}
function checkUnsafeE(r) {
  assert.ok(r.options.readOnly&&r.options.unsafeSpareE);
  const entry=rows(r,'read-0/upper-after-4').find(e=>e.ip===0xD6);
  assert.ok(entry);assert.equal(entry.slot,'T');
  assert.equal(raw(entry.m,0),r.beforeRegisters[14]);
  assert.notEqual(raw(entry.m,0),'000020000000','the old E payload really reaches the pointer reader');
  const copies=p.brief(r).copies;
  assert.ok(copies.some(x=>x.actual!==x.expected),'omitting E preparation must not silently pass as a complete reader');
  return {firstPointer:{slot:entry.slot,word:raw(entry.m,0)},failedCopies:copies.filter(x=>x.actual!==x.expected).map(x=>x.word)};
}
function checkLateGuardFailure(r) {
  const es=r.traced.events,source=r.before.P7.slice(2);
  const spill=es.findIndex(e=>e.stage==='read-2/upper-after-5'&&e.ip===0xE7&&e.slot==='U');assert.ok(spill>=0);
  const block=checkSwapBlock(r,spill,1);assert.equal(raw(block.body[0].r,0),guard);assert.equal(block.after.ip,0x47);
  assert.equal(raw(at(r,'read-final-a/exchange-wq/clear-before').ring.Q),source);
  const bad=rows(r,'read-final-a/exchange-wq/shifted-swap');
  const accepted=bad.find(e=>e.ip===0x9C&&e.slot==='U'&&e.nextIp===0x9E);assert.ok(accepted);assert.equal(accepted.raw,guard);
  assert.ok(!bad.some(e=>e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='W'),'the required W/Q exchange is not called');
  assert.equal(raw(at(r,'save-a-in-c').ring.control,0),'2F8000000000');
  for(const n of names.filter(n=>n!=='P7'))assert.equal(r.after[n],r.before[n]);
  assert.equal(r.after.P7,r.before.P7.slice(0,2)+'2F8000000000');
  assert.equal(r.afterRegisters[10],'2F8000000000');
  for(const x of p.brief(r).copies.filter(x=>x.word!=='P7'))assert.equal(x.actual,x.expected);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  return {spill:'E7(U)',accepted:'9C(U)->9E',lost:'P7',replacement:'2F8000000000'};
}
function checkLegacyLowerReturn(r) {
  const es=r.traced.events,source=r.before.Q.slice(2);
  const completed=rows(r,'backup-four/read-q/shifted-swap').find(e=>e.otherChips?.[4].ip===0x53&&e.otherChips[4].slot==='W'&&e.otherChips[4].r[32]===5);
  assert.ok(completed);assert.equal(raw(completed.otherChips[4].m),source);
  const second=checkSwapBlock(r,es.findIndex(e=>e.stage==='backup-four/read-q/post-swap-1'&&e.ip===0xE7&&e.slot==='X'&&e.nextIp===0xA8),4);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(second.after.ring[n])),[zero,zero,source,source]);
  const one=rows(r,'backup-four/read-q/post-swap-2'),i=one.findIndex(e=>e.otherChips?.[4].ip===0x3A&&e.otherChips[4].slot==='X');assert.ok(i>=0);
  const block=one.slice(i,i+5),initial=block[0].ring,expected=structuredClone(initial),visible=['X','Y','Z','T'];
  assert.deepEqual(block.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x3A,'X'],[0x3A,'Y'],[0x3A,'Z'],[0x2A,'T'],[0x39,'U']]);
  for(let n=0;n<4;n++)for(let j=0;j<12;j++)expected[visible[n]][1+3*j]=initial[visible[(n+1)%4]][1+3*j];
  assert.deepEqual(block[4].ring,expected);assert.equal(raw(expected.X),zero);
  const written=r.traced.writes.filter(w=>w.command>=block[0].command&&w.command<block[4].command);
  assert.equal(written.length,48);assert.ok(written.every(w=>w.chip===4&&visible.includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
  assert.equal(raw(at(r,'backup-four/save-q-to-p6').ring.control,0),zero);
  assert.equal(r.afterRegisters[13],zero);assert.equal(r.after.Q,r.before.Q.slice(0,2)+zero);
  for(const n of names.filter(n=>n!=='Q'))assert.equal(r.after[n],r.before[n]);
  for(const x of p.brief(r).copies.filter(x=>x.word!=='Q'))assert.equal(x.actual,x.expected);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  return {beforeRotation:[zero,zero,source,source],legacyX:zero,lost:'Q'};
}
function negativeB() {
  // Functional native counterexample only: no passive ROM trace, so this
  // check establishes failure of the full protocol, not its first cause.
  const {fullMsPages}=require('./probe_c8_payload.cjs');
  const {registers,program}=require('./probe_a8_ms_readout.cjs');
  const options={fullUpper:['1111','-1E-99','3333','4444']};
  const c=p.prepare(options),before=fullMsPages(c),beforeProgram=program(c);
  assert.equal(before.P8.slice(2),'901910000000');
  p.finish(c,options);c.runFrames(3);aligned(c);
  const after=fullMsPages(c),regs=registers(c);
  assert.notDeepEqual(after,before);assert.deepEqual(program(c),beforeProgram);
  const failed=[1,5,11,13,10,8,14,6].flatMap((reg,i)=>regs[reg]===before[names[i]].slice(2)?[]:[names[i]]);
  assert.ok(failed.length>0);assert.equal(after.V.slice(2),marker,'a hidden marker survives the failed return');
  return {options,failedCopies:failed,display:c.displayText(),programPreserved:true};
}
function main() {
  const negative=process.env.MS_READ8_NEGATIVE_ONLY;
  if(negative) {
    assert.ok(['unsafe-e','late-guard','lower-return','negative-b'].includes(negative));
    if(negative==='negative-b'){console.log('PASS negative-b:',JSON.stringify(negativeB()));return;}
    const r=p.run(negative==='unsafe-e'?{readOnly:true,unsafeSpareE:true,legacyLowerReturn:true}:
      negative==='lower-return'?{...complex,settleFrames:12,markerFrames:8,legacyLowerReturn:true}:
      {...complex,phaseOffset:2,postPointer:'111',legacyLowerReturn:true});
    console.log('PASS negative:',negative,JSON.stringify(negative==='unsafe-e'?checkUnsafeE(r):negative==='lower-return'?checkLegacyLowerReturn(r):checkLateGuardFailure(r)));release(r);return;
  }
  const from=Number(process.env.MS_READ8_FROM??0),count=Number(process.env.MS_READ8_CASES??cases.length);
  const controlsOnly=process.env.MS_READ8_CONTROLS_ONLY==='1';
  let first=controlsOnly?process.env.MS_READ8_EXPECTED_DIGEST:undefined;
  if(controlsOnly)assert.ok(first,'controls-only requires a digest from a completed observed baseline');
  for(const o of controlsOnly?[]:cases.slice(from,from+count)) {
    const r=p.run(o),observed=digest(r.calc);first??=observed;
    console.log('PASS read8:',JSON.stringify(o),JSON.stringify(check(r)),'DIGEST',observed);release(r);
  }
  if(from||count<cases.length)return;
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);assert.equal(digest(plain),first);
  console.log('PASS observed/unobserved:',first);
  const repeated=p.runPrepared(plain,{phaseOffset:1});check(repeated);release(repeated);
  console.log('PASS full repeat without reset, import or fixture reseeding.');
  const readOnly=p.run({readOnly:true});check(readOnly);release(readOnly);
  console.log('PASS independent eight-copy reader with explicit lower cleanup.');
  const bad=p.run({readOnly:true,unsafeSpareE:true,legacyLowerReturn:true});console.log('PASS unsafe-E negative control:',JSON.stringify(checkUnsafeE(bad)));release(bad);
  const badLate=p.run({...complex,phaseOffset:2,postPointer:'111',legacyLowerReturn:true});console.log('PASS late-guard negative control:',JSON.stringify(checkLateGuardFailure(badLate)));release(badLate);
  const badLower=p.run({...complex,settleFrames:12,markerFrames:8,legacyLowerReturn:true});console.log('PASS lower-return negative control:',JSON.stringify(checkLegacyLowerReturn(badLower)));release(badLower);
  console.log('PASS negative-b:',JSON.stringify(negativeB()));
  console.log('LIMIT: eight simultaneous numeric readouts plus Ms restoration, not exchange with the original ordinary-register bank or a universal native K1.');
}
if(require.main===module)main();
module.exports={check,checkReader,checkMarkerCarrier,checkLowerBackup,checkBufferBridge,checkUnsafeE,checkLateGuardFailure,checkLegacyLowerReturn,negativeB,cases,complex};
