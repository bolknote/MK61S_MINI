#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_lower_secondary_exchange.cjs');
const base=require('./check_ms_lower_exchange.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSecondaryWRead}=require('./check_ms_upper_roundtrip.cjs');
const {checkLowerPush}=require('./check_ms_read6_roundtrip.cjs');
const {ordinaryChecks}=require('./check_ms_upper_read4.cjs');
const check=(r,o={})=>base.check(r,{...o,secondaryW:true});
const oldCounter={values:['-1E-99','-1.2345678E-42','-9.8765432E99','-1E-99']};
// The third phase of oldCounter is deliberately a NEGATIVE test below.
// Improving W's source selection does not fix the W/Q bridge's scanner.
const cases=[{},...[0,1].map(phaseOffset=>({...oldCounter,phaseOffset})),
  {...base.complex,phaseOffset:2},{...base.complex,settleFrames:12,markerFrames:8},
  {bank:['0','0','0','0'],values:['0','0','0','0']}];
function checkNegativeQ(r,{post=true}={}) {
  const names=['U','V','W','Q'],upper=['P7','P8','P9','P10'];
  const words=names.map(n=>r.before[n].slice(2)),old=r.beforeRegisters;
  const copies=[...words.slice(0,3),words[2]];
  assert.equal(r.options.phaseOffset,2);assert.equal(words[0],'901910000000');
  assert.notEqual(words[2],words[3],'different W and Q make the failure observable');
  assert.deepEqual(r.after,{...r.before,...Object.fromEntries(names.map((n,i)=>[n,r.before[n].slice(0,2)+old[i]]))});
  assert.deepEqual(r.afterRegisters,[...copies,...old.slice(4,9),old[0],...copies,old[3]]);
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  base.checkU(r);base.checkDirect(r,'read-v/',words[1],'V',2);
  const wOverlap=checkSecondaryWRead(r,'read-w/',words[2],'keep-w-in-c');
  const rows=label=>r.traced.events.filter(e=>e.stage===label);
  const at=label=>{const e=rows(label).find(e=>e.ring);assert.ok(e,label);return e;};
  const stage='read-last/exchange-wq/shifted-swap',swap=rows(stage);
  const guard=swap.find(e=>e.ip===0x9C&&e.slot==='U');assert.ok(guard);
  assert.equal(guard.raw,words[0]);assert.equal(guard.nextIp,0x9E);
  const request=swap.find(e=>e.ip===0xA3);assert.ok(request);
  assert.equal(request.slot,'control','the request is NOT submitted in U');
  const ai=swap.findIndex(e=>e.ip===0xA2);
  const search=swap.slice(ai,swap.indexOf(request));
  assert.deepEqual(search.map(e=>[e.ip,e.slot]),
    ['W','Q','P7','P8','P9','P10','marker'].map(n=>[0xA2,n]));
  assert.ok(search.every((e,i)=>e.command===search[0].command+i));
  assert.equal(request.command,search.at(-1).command+1);
  const pi=swap.findIndex(e=>e.otherChips?.[4].ip===0x4E);assert.ok(pi>=0);
  const pair=swap.slice(pi,pi+3),before=pair[0].ring,after=structuredClone(before);
  assert.deepEqual(pair.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [[0x4E,'X'],[0x2A,'Y'],[0x39,'Z']]);
  for(let j=0;j<12;j++){
    after.X[1+3*j]=pair[0].otherChips[4].r[3*j];
    after.Y[1+3*j]=before.X[1+3*j];
  }
  assert.deepEqual(pair[2].ring,after,'the wrong visible pair is still an exact ROM transfer');
  const pairWrites=r.traced.writes.filter(w=>w.command>=pair[0].command&&w.command<pair[2].command);
  assert.equal(pairWrites.length,24);
  assert.ok(pairWrites.every(w=>w.chip===4&&['X','Y'].includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
  assert.equal(swap.filter(e=>e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='W').length,0);
  const begin=at('read-last/exchange-wq/clear-before'),end=at('read-last/read-q/clear-before');
  assert.deepEqual(['U','W','Q'].map(n=>raw(end.ring[n])),[words[0],words[2],words[3]]);
  assert.deepEqual(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&
    ['W','Q',...upper].includes(w.slot)&&w.nibble%3===1&&w.value!==w.before),[]);
  assert.equal(raw(begin.ring.Y,0),words[2],'C holds the correct W before the bridge fails');
  const qOverlap=checkSecondaryWRead(r,'read-last/read-q/',words[2],'keep-q-in-d');
  for(const [key,index] of [['В↑',3],['2',2],['1',1],['0',0]])checkLowerPush(r,'write-'+key+'/',old[index]);
  assert.deepEqual(r.traced.writes.filter(w=>upper.includes(w.slot)&&w.nibble%3===1&&w.value!==w.before),[]);
  if(post)ordinaryChecks(r);
  return {control:guard.command,request:request.command,wrongPair:pair[0].command,wOverlap,qOverlap};
}
function negativeQ() {
  const r=p.run({...oldCounter,phaseOffset:2});
  console.log('PASS negative Q entry:',JSON.stringify(checkNegativeQ(r)));base.release(r);
  console.log('LIMIT: W is correct, but 9C(U)->9E submits the request in true control; X/Y swap instead of W/Q, so the incoming Q copy is old W.');
}
function controls(expected) {
  assert.match(expected??'',/^[0-9a-f]{64}$/);
  const plain=p.prepare(),before=fullMsPages(plain),beforeRegisters=registers(plain),beforeProgram=program(plain);
  p.finish(plain);plain.runFrames(3);aligned(plain);assert.equal(digest(plain),expected);
  console.log('PASS observed/unobserved full core:',expected);
  const back=p.runPrepared(plain,{phaseOffset:1});console.log('PASS baseline return paths:',JSON.stringify(check(back)));
  assert.deepEqual(back.after,before);assert.deepEqual(back.afterRegisters.slice(0,9),beforeRegisters.slice(0,9));
  assert.deepEqual(back.afterProgram,beforeProgram);base.release(back);
  console.log('PASS two applications restore all Ms, P0..P8 and program; scratch P9..E excluded.');
}
function main() {
  if(process.env.MS_SECONDARY_EXCHANGE_NEGATIVE_Q_ONLY==='1')return negativeQ();
  if(process.env.MS_SECONDARY_EXCHANGE_CONTROLS_ONLY==='1')return controls(process.env.MS_SECONDARY_EXCHANGE_EXPECTED_DIGEST);
  const from=Number(process.env.MS_SECONDARY_EXCHANGE_FROM??0),count=Number(process.env.MS_SECONDARY_EXCHANGE_CASES??cases.length);
  let firstDigest;const wOverlaps=new Set(),qOverlaps=new Set();
  for(const o of cases.slice(from,from+count)) {
    const r=p.run(o),d=digest(r.calc);if(from===0)firstDigest??=d;
    const path=check(r);qOverlaps.add(path.overlap);wOverlaps.add(path.wOverlap);
    console.log('PASS secondary-W exchange:',JSON.stringify(o),JSON.stringify(path));console.log('OBSERVED_DIGEST',d);base.release(r);
  }
  console.log('COVERAGE',JSON.stringify({from,count:Math.min(count,cases.length-from),wOverlaps:[...wOverlaps],qOverlaps:[...qOverlaps],firstDigest}));
  if(from||count<cases.length)return;controls(firstDigest);negativeQ();
  console.log('LIMIT: conditional lower four-pair exchange, NOT full K1 or universal keyboard reachability; original scratch registers not restored.');
}
if(require.main===module)main();
module.exports={check,checkNegativeQ,negativeQ,oldCounter,cases,controls,release:base.release};
