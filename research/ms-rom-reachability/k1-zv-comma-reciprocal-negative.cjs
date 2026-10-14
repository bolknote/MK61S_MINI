#!/usr/bin/env node
'use strict';
// The original 1/x exit is not valid for arbitrary ordinary R8.
// A keyboard fixture R8=125 exposes the exact competing writes to X.
const assert=require('node:assert/strict');
const probe=require('./k1-zv-comma-closed.cjs');
const transfer=require('./k1-zv-comma-transfer-check.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=assert.deepEqual,negative='002912500000',reciprocal='997980000000';
const copy=(c,chip,n,v)=>[...v].reverse().map((x,j)=>[c,chip,n,1+3*j,parseInt(x,16)]);
const key=w=>[w.command,w.chip,w.slot,w.nibble,w.value];
const ordered=xs=>xs.toSorted((a,b)=>a[0]-b[0]||a[1]-b[1]||a[3]-b[3]);
const options={...probe.defaults,fixtureRegisters:{8:'125'},
  afterTransfer:[['/-/'],['F','/']],afterTransferPhases:[0,0]};
function check(r) {
  same(r.options.afterTransfer,options.afterTransfer);
  same(r.options.afterTransferPhases,options.afterTransferPhases);
  same(r.beforeRegisters[8],'002012500000');
  const initial=snapshotFromRing(r.traced.events.find(e=>e.ring).ring);
  same(new Set(initial.words).size,23);
  const prefix=transfer.check(prefixView(r,'comma/tail-0',{afterTransfer:[],afterTransferPhases:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);same(r.beforeProgram,r.afterProgram);
  const at=s=>checks.boundary(r,s),events=s=>r.traced.events.filter(e=>e.stage===s);
  const sign=events('comma/tail-0'),sg=sign.filter(e=>e.ip===0xE7);
  same(sign.filter(e=>e.ip===0xEE).map(e=>[e.slot,e.raw,e.nextIp]),[['V',r.beforeRegisters[8],0xC1]]);
  same(sg.length,1);repack.exactCopy(r,sg[0],'X',negative);
  const before=at('comma/tail-0'),input=at('comma/tail-1'),end=at('done');
  const expectedSign=structuredClone(before.ring);deep.word(expectedSign,'X',negative);
  same(input.ring,expectedSign);
  same(r.traced.writes.filter(w=>w.command>=before.command&&w.command<input.command).map(key),
    copy(sg[0].command,3,'X',negative));
  const es=events('comma/tail-1'),ww=r.traced.writes.filter(w=>w.command>=input.command&&w.command<end.command);
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['T',0x9E],['T',0x9E]]);
  same(es.filter(e=>e.ip===0xEE).map(e=>[e.slot,e.raw,e.nextIp]),[['X',negative,0xA1],['X',negative,0xE3]]);
  const one=ip=>{const found=es.filter(e=>e.ip===ip);same(found.length,1);return found[0];};
  const save=one(0xE9),request=one(0xA3),late=one(0xE7);
  same(request.slot,'control');repack.exactCopy(r,save,'U',negative);repack.exactCopy(r,late,'X',negative);
  const secondary=ww.filter(w=>w.chip===4),ack=secondary.filter(w=>w.ip===0x27),out=secondary.filter(w=>w.ip!==0x27);
  same(ack.map(w=>[w.slot,w.nibble,w.value]),[['control',31,15]]);same(out.length,12);
  const output=out[0].command;same(out.map(w=>[w.ip,...key(w)]),copy(output,4,'X',reciprocal).map(v=>[0x2A,...v]));
  same(output,request.command+48);same(late.command,output+29);
  const resultRing=ringAt(r,output),expectedResult=structuredClone(resultRing);deep.word(expectedResult,'X',reciprocal);
  same(ringAt(r,output+1),expectedResult,'the reciprocal really exists before the late copy');
  same(raw(ringAt(r,late.command).X),reciprocal);same(raw(ringAt(r,late.command+1).X),negative);
  const hv=[2,3,2],expected=structuredClone(input.ring);
  deep.word(expected,'U',negative);[28,31,34].forEach((n,j)=>{expected.control[n]=hv[j];});expected.control[31]=15;
  same(end.ring,expected,'all 630 tetras: the reciprocal is erased, original input remains in X');
  same(ordered(ww.map(key)),ordered([...copy(save.command,3,'U',negative),
    ...[28,31,34].map((n,j)=>[request.command,3,'control',n,hv[j]]),
    [ack[0].command,4,'control',31,15],...copy(output,4,'X',reciprocal),...copy(late.command,3,'X',negative)]));
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  same(raw(end.ring.Y),r.before.U.slice(2));
  return {prefix,request:request.command,reciprocalOutput:output,lateOverwrite:late.command,
    resultErasedAfterCommands:29,all23StillLive:true,closedExit:false,
    rejectsOnlyThisReciprocalSuffix:true,fullStateCollisionClaimed:false};
}
if(require.main===module) {
  console.log('PASS surface:',JSON.stringify(deep.surface(options,probe.finish)));
  const r=probe.traced(options);console.log('PASS reciprocal counterexample:',JSON.stringify(check(r)));
  if(process.env.K1_COMMA_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={options,check};
