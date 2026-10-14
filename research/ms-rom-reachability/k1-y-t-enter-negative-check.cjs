#!/usr/bin/env node
'use strict';
// One native negative continuation, not a global ENTER/K1 impossibility.
const assert=require('node:assert/strict');
const probe=require('./k1-y-t-entry.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const values=e=>Object.fromEntries(Object.entries(e.ring).map(([n,t])=>[n,raw(t)]));
function audit(r) {
  same(r.options.afterClone,[['В↑']]);
  const at=checks.boundary(r,'after-clone-0'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='after-clone-0');
  const u=r.before.U.slice(2),v=r.before.V.slice(2),q=r.before.Q.slice(2);
  same(['X','Y','Z','T','U','V','W','Q'].map(n=>values(at)[n]),
    [v,'9990FFFFFFF0',q,'9990FFFFFFF0',v,u,q,r.beforeRegisters[0]],'entry payload geometry');
  const transfers=es.filter(e=>[0x9C,0xEE,0xE7,0xE9,0xA3,0xA7,0xA8,0xA9].includes(e.ip))
    .map(e=>({command:e.command,ip:e.ip.toString(16),slot:e.slot,next:e.nextIp.toString(16),raw:e.raw}));
  const changed=r.traced.writes.filter(e=>e.command>=at.command&&e.command<end.command&&e.before!==e.value);
  const unique=[...new Set(changed.map(e=>e.command))].map(command=>({command,
    event:es.filter(e=>e.command===command).map(e=>({ip:e.ip.toString(16),slot:e.slot,raw:e.raw})),
    writes:changed.filter(e=>e.command===command).map(e=>({chip:e.chip,slot:e.slot,nibble:e.nibble,before:e.before,value:e.value}))}));
  const lost=repack.boundaryLosses(r).filter(e=>e.command>=at.command);
  return {at:at.command,end:end.command,before:values(at),after:values(end),transfers,changed:unique,lost};
}
function check(r) {
  same(r.options.afterClone,[['В↑']]);
  assert.ok(!r.options.afterClonePhase,'no extra lead frames in this tested continuation');
  same(r.options.clonePrefix,[]);same(r.options.cloneKeys,['↔']);same(r.options.clonePhase,0);
  const at=checks.boundary(r,'after-clone-0'),end=checks.boundary(r,'done');
  const es=r.traced.events.filter(e=>e.stage==='after-clone-0');
  const u=r.before.U.slice(2),v=r.before.V.slice(2),q=r.before.Q.slice(2),m='9990FFFFFFF0';
  same(['X','Y','Z','T','U','V','W','Q'].map(n=>values(at)[n]),
    [v,m,q,m,v,u,q,r.beforeRegisters[0]],'entry payload geometry');
  checks.protectedFields(r,[0],['U','V','W','Q']);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:r.before.W.slice(2)));
  const gates=es.filter(e=>e.ip===0x9C);same(gates.length,1);
  same([gates[0].slot,gates[0].nextIp,gates[0].raw],['control',0x9E,'3F0000000000']);
  const reads=es.filter(e=>e.ip===0xEE);same(reads.length,2);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['U',v,0xE0],['X',v,0xE3]]);
  same(es.filter(e=>[0xE9,0xA3].includes(e.ip)),[],'no early save or secondary request');
  const push=checks.exactPush(r,'after-clone-0',['X','Y','Z','T']);same(push.displaced,m);
  const late=es.find(e=>e.command>reads[1].command&&e.ip===0xE7);assert.ok(late);
  same([late.slot,late.raw,raw(late.r,0)],['V',u,v]);
  repack.exactCopy(r,late,'V',v);
  const changed=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command&&w.before!==w.value);
  for(const w of changed) {
    const i=w.command-push.command;
    assert.ok(w.chip===3&&w.nibble%3===1&&w.nibble<37&&
      ((i>=0&&i<4&&w.slot===['X','Y','Z','T'][i])||(w.command===late.command&&w.slot==='V')),
      'undeclared changed tetra in complete ENTER: '+JSON.stringify(w));
  }
  const expected=structuredClone(at.ring);
  for(const [n,val] of Object.entries({X:v,Y:v,Z:m,T:q,V:v}))
    [...val].reverse().forEach((digit,j)=>{expected[n][1+3*j]=parseInt(digit,16);});
  same(end.ring,expected,'all 630 tetras: only declared visible push and V copy');
  const available=ring=>[...snapshotFromRing(ring).words,...['X1','X','Y','Z','T'].map(n=>raw(ring[n]))];
  const before=ringAt(r,late.command),after=ringAt(r,late.command+1);
  same(available(before).filter(x=>x===u),[u],'u is the sole stored/visible copy before late E7');
  assert.ok(!available(after).includes(u),'late E7 removes the last stored/visible u');
  assert.ok(r.traced.writes.filter(w=>w.command>=at.command&&w.command<late.command&&
    w.slot==='V'&&w.nibble%3===1&&w.nibble<37).every(w=>w.before===w.value),
    'V remains exact u until the late E7');
  const first=changed.find(w=>w.slot==='V');
  same([first.command,first.chip,first.ip,first.nibble,first.before,first.value],
    [late.command,3,0xE7,1,8,2],'first destructive tetra of original u');
  const loss=repack.boundaryLosses(r).filter(e=>e.missing.length);
  same(loss.map(e=>[e.stage,e.missing]),[['done',[u]]]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['Z','marker']);
  return {rejected:'this exact ENTER continuation',control:gates[0].command,
    readU:reads[0].command,push,lateReadX:reads[1].command,destructiveE7V:late.command,
    firstChangedTetra:first,oldUAbsentFromStoredAndVisible:true,onlyRealAndZMarkers:true,
    programAndServiceFieldsHeld:true,other14OrdinaryAndUpper4Held:true,
    noE9OrSecondaryRequest:true,notGlobalImpossibility:true};
}
if(require.main===module) {
  const r=probe.run({afterClone:[['В↑']]});
  console.log('PASS exact negative ENTER:',JSON.stringify(check(r)));
  if(process.env.K1_Y_T_ENTER_AUDIT)console.log(JSON.stringify(audit(r),null,2));
  if(process.env.K1_Y_T_ENTER_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={audit,check};
