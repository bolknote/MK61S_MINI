#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zv-comma-transfer.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=assert.deepEqual,m='9990FFFFFFF0';
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
function exactWrites(r,from,to,groups) {
  const at=checks.boundary(r,from),end=checks.boundary(r,to);
  same(r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command)
    .map(w=>[w.command,w.chip,w.slot,w.nibble]),
    groups.flatMap(([c,n])=>Array.from({length:12},(_,j)=>[c,3,n,1+3*j])));
}
function expectedTransfer(r,ring) {
  const expected=structuredClone(ring),a=r.before.P7.slice(2);
  deep.word(expected,'V',r.beforeRegisters[8]);deep.word(expected,'W',a);
  deep.word(expected,'Q',raw(ring.W));deep.word(expected,'P7',raw(ring.Q));
  return expected;
}
function frameCheck(r) {
  const initial=snapshotFromRing(r.initial),at=s=>r.rows.find(e=>e.stage===s);
  same(new Set(initial.words).size,23);same(r.rows.filter(e=>e.missing.length),[]);
  for(const e of r.rows) {
    const s=snapshotFromRing(e.ring);same(s.program,initial.program);same(s.services,initial.services);
    same(s.words.slice(1,15),initial.words.slice(1,15));same(s.words.slice(20),initial.words.slice(20));
    same(e.values.marker,'000FFFFFFFFF');
  }
  const before=at('comma'),copy=at('comma/transfer'),expected=structuredClone(before.ring);
  deep.word(expected,'V',r.before.P7.slice(2));same(copy.ring,expected);
  for(const stage of ['immediate','done']) {
    same(at(stage).ring,expectedTransfer(r,copy.ring));same(marks(at(stage)),['Z','marker']);
  }
  return {boundaries:r.rows.length,all23Live:true,shortAInW:true,upperBCDProtected:true,workingExit:false};
}
function check(r) {
  same(r.options.afterTransfer,[]);same(r.options.deepTail,probe.defaults.deepTail);
  const prefix=deep.check(prefixView(r,'deep/tail-1',{deepTail:[['K','0']],deepTailPhases:[1]}));
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  const a=r.before.P7.slice(2),u=r.before.U.slice(2),v=r.before.V.slice(2);
  assert.match(a,/^0020[1-9][0-9][1-9]00000$/,'positive three-digit class 6');
  const at=s=>checks.boundary(r,s),es=s=>r.traced.events.filter(e=>e.stage===s);
  for(const s of ['deep/tail-1','comma','comma/transfer'])assert.ok(es(s).every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  const enter=es('deep/tail-1'),er=enter.filter(e=>e.ip===0xEE),el=enter.filter(e=>e.ip===0xE7&&e.nextIp===0x47);
  same(enter.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);
  same(er.map(e=>[e.slot,e.raw,e.nextIp]),[['U',u,0xE0],['P7',a,0xE3]]);same(el.length,1);
  const ep=checks.exactPush(r,'deep/tail-1',['X','Y','Z','T']);same(ep.displaced,m);repack.exactCopy(r,el[0],'X',a);
  exactWrites(r,'deep/tail-1','comma',[...['X','Y','Z','T'].map((n,i)=>[ep.command+i,n]),[el[0].command,'X']]);
  const expectedEnter=structuredClone(at('deep/tail-1').ring);
  for(const [n,value] of [['X',a],['Y',u],['Z',m],['T',v]])deep.word(expectedEnter,n,value);
  same(at('comma').ring,expectedEnter);

  const ce=es('comma'),gates=ce.filter(e=>e.ip===0x9C),writes=ce.filter(e=>e.ip===0xE7);
  if(process.env.K1_COMMA_DIAGNOSTIC)console.log('COMMA gate:',JSON.stringify(gates.map(e=>({command:e.command,slot:e.slot,r:e.r,st:e.st,s:e.s,s1:e.s1}))));
  same(gates.map(e=>[e.slot,e.nextIp]),[['T',0x9E]]);same(writes.length,1);
  same(ce.filter(e=>[0xEE,0xE9,0xA3,0xA8,0xD4,0xD6].includes(e.ip)),[]);
  const gate=gates[0];
  const rv=[15,2,0,15,3,10,15,4,10,15,5,10,15,6,10,2,7,10,0,8,10,4,9,0,15,9,0,15,9,10,10,5,0,0,2,15,12,2,13,9,6,0];
  const st=[0,10,0,0,10,8,0,10,8,0,10,8,0,10,8,2,10,8,0,10,8,4,0,0,0,0,0,15,2,0,15,0,0,15,0,0,10,8,15,9,9,4];
  for(const [j,i] of [15,18,21].entries())rv[i]=st[i]=parseInt(a[6-j],16);
  const freeR=new Set([1,4,7,10,13,16,19,28]),mask=xs=>xs.map((x,i)=>freeR.has(i)?null:x);
  same(mask(gate.r),mask(rv),'symbolic cache premises R');same(gate.st,st,'symbolic cache premises ST');same([gate.s,gate.s1],[12,10]);
  deep.path(ce,gate.command,'T',deep.ips('9C 9E 8C 91 92 93 94 95 98 9A 93 94 95 98 9A 8D 4F AF AE DC EA EC 40 41 42 46 E5 E5 E5 E5 E6 E8 E7'));
  repack.exactCopy(r,writes[0],'V',a);exactWrites(r,'comma','comma/transfer',[[writes[0].command,'V']]);
  const copied=structuredClone(expectedEnter);deep.word(copied,'V',a);same(at('comma/transfer').ring,copied);
  same(marks(at('comma/transfer')),['Z','marker']);

  const te=es('comma/transfer'),tr=te.filter(e=>e.ip===0xEE),tl=te.filter(e=>e.ip===0xE7&&e.nextIp===0x47),d6=te.filter(e=>e.ip===0xD6);
  same(te.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);
  same(tr.map(e=>[e.slot,e.raw,e.nextIp]),[['V',a,0xAB],['X',a,0xE3]]);same([tl.length,d6.length],[1,1]);
  same(te.filter(e=>[0xE9,0xA3,0xD4].includes(e.ip)),[]);same(d6[0].slot,'marker');
  same(raw(ringAt(r,d6[0].command).marker,0),r.beforeRegisters[8]);
  const push=checks.exactPush(r,'comma/transfer',['V','W','Q','P7']);same(push.displaced,a);
  repack.exactCopy(r,tl[0],'X',a);
  exactWrites(r,'comma/transfer','done',[...['V','W','Q','P7'].map((n,i)=>[push.command+i,n]),[tl[0].command,'X']]);
  same(at('done').ring,expectedTransfer(r,copied),'all 630 transfer endpoint tetras');same(marks(at('done')),['Z','marker']);
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  const end=at('done'),original=snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words;
  same(original.filter(x=>!snapshotFromRing(end.ring).words.includes(x)),[v]);
  same(['X1','X','Y','Z','T'].filter(n=>raw(end.ring[n])===v),['T']);
  return {prefix,boundaries:rows.length,enter:el[0].command,commaGate:gate.command,commaCopy:writes[0].command,
    upperPush:push.command,lateCopyX:tl[0].command,only12CommaAnd60TransferWrites:true,
    wholeFrameWaitsOnly:true,all23Live:true,shortAInW:true,upperBCDProtected:true,
    extraMarkers:['Z'],vOnlyInT:true,workingExit:false,arbitraryNumbersProved:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_COMMA_OPTIONS||'{}')};
  console.log('PASS surface:',JSON.stringify(deep.surface(o,probe.finish)));
  if(!process.env.K1_COMMA_SKIP_FRAME)console.log('PASS frames:',JSON.stringify(frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS native:',JSON.stringify(check(r)));
  if(process.env.K1_COMMA_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={frameCheck,check,exactWrites};
