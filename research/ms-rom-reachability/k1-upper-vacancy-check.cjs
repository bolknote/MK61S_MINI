#!/usr/bin/env node
'use strict';
// Native full-write contract for the baseline fixture only.
const assert=require('node:assert/strict');
const probe=require('./k1-upper-vacancy.cjs');
const upper=require('./k1-preserving-upper-rotation-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {M1_SLOTS,PLACES,snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const zero='000000000000';
const values=e=>Object.fromEntries(Object.entries(e.ring).map(([n,t])=>[n,raw(t)]));
function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,initialPhaseOffsetExcluded:true,assumedSuccessfulAttempts:1};
}
function check(r) {
  same(r.options.upperLeadPhase,1);same(r.options.afterUpperPhase,1);
  same(r.options.afterUpper,[['K','8'],['F','В↑']]);same(r.options.afterUpperWaits,[8,8]);
  const names=['U','V','W','Q','P7','P8','P9','P10'];
  const originals=names.map(n=>r.before[n].slice(2));
  same(originals,['007912345678','983998765432','977976543210','958912345678',
    '003090110000','003090220000','003090330000','003090440000'],
    'this contract covers only the explicitly tested baseline numerical fixture');
  same(r.beforeRegisters[0],'002020100000');
  const [u,v,w,q,a,b,c,d]=originals,p=r.beforeRegisters[0];
  checks.protectedFields(r,[0],Object.keys(r.before));
  const at=checks.boundary(r,'after-upper-0'),middle=checks.boundary(r,'after-upper-1');
  const end=checks.boundary(r,'done');
  // Read-only prefix view; no native state import or shortened execution.
  const prefix=upper.check({...r,options:{...r.options,afterUpper:[]},
    after:Object.fromEntries(names.map(n=>[n,raw(at.ring[n],1,14)])),
    afterRegisters:M1_SLOTS.map(n=>raw(at.ring[n],0)),
    traced:{...r.traced,writes:r.traced.writes.filter(e=>e.command<at.command),
      events:r.traced.events.filter(e=>e.command<=at.command)
        .map(e=>e===at?{...e,stage:'done'}:e)}});
  const es=r.traced.events.filter(e=>e.stage==='after-upper-0');
  const ctrl=es.find(e=>e.ip===0x9C);assert.ok(ctrl);
  same([ctrl.slot,ctrl.nextIp],['control',0x9E]);
  const read=es.find(e=>e.ip===0xEE&&e.nextIp===0xA1);assert.ok(read);
  same([read.slot,read.raw],['P7',b]);
  const copy=es.find(e=>e.ip===0xE9);repack.exactCopy(r,copy,'X1',b);
  const request=es.find(e=>e.ip===0xA3);assert.ok(request);same(request.slot,'W');
  const wantRequest=ringAt(r,request.command);
  for(const [n,value] of [[34,3],[31,5],[28,3]])wantRequest.W[n]=value;
  same(ringAt(r,request.command+1),wantRequest,'exact K8 request among all 630 tetras');
  same(r.traced.writes.filter(w=>w.command===request.command).map(w=>[w.chip,w.slot,w.nibble]),
    [[3,'W',28],[3,'W',31],[3,'W',34]]);
  const lateRead=es.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(lateRead);
  same([lateRead.slot,lateRead.raw],['P7',b]);
  const late=es.find(e=>e.command>lateRead.command&&e.ip===0xE7);
  repack.exactCopy(r,late,'X',b);
  same(values(middle),{...values(at),P7:zero,W:'3F3912345678',X1:b,X:b});
  const fraction=r.traced.writes.filter(w=>w.command>=at.command&&w.command<middle.command&&
    w.chip===5&&w.before!==w.value);
  const acknowledged=fraction.filter(w=>w.slot==='W');
  same(acknowledged.map(w=>[w.ip,w.nibble,w.before,w.value]),[[0xFD,31,5,15]]);
  const ack=acknowledged[0],wantAck=ringAt(r,ack.command);wantAck.W[31]=15;
  same(ringAt(r,ack.command+1),wantAck,'IK1306 FD changes only the request acknowledgement tetra');
  const cleared=fraction.filter(w=>w.slot==='P7');assert.ok(cleared.length);
  assert.ok(cleared.every(w=>w.ip===0xFF&&w.nibble%3===1&&w.nibble<37&&w.value===0));
  const clearCommands=[...new Set(cleared.map(w=>w.command))];same(clearCommands.length,1);
  const clearCommand=clearCommands[0],wantClear=ringAt(r,clearCommand);
  same(raw(wantClear.P7),b);
  for(let j=0;j<12;j++)wantClear.P7[1+3*j]=0;
  same(ringAt(r,clearCommand+1),wantClear,'IK1306 FF clears P7 and holds all other 618 tetras');
  assert.ok(copy.command<late.command&&late.command<ack.command&&ack.command<clearCommand,
    'both X1 and X back up b before its P7 copy is cleared');
  for(const wr of r.traced.writes.filter(w=>w.command>=at.command&&w.command<middle.command&&w.before!==w.value))
    assert.ok((wr.chip===5&&wr.command===clearCommand&&wr.ip===0xFF&&wr.slot==='P7'&&
        wr.nibble%3===1&&wr.nibble<37&&wr.value===0)||
      (wr.chip===5&&wr.command===ack.command&&wr.ip===0xFD&&wr.slot==='W'&&wr.nibble===31&&wr.value===15)||
      (wr.chip===3&&((wr.command===copy.command&&wr.slot==='X1')||
        (wr.command===late.command&&wr.slot==='X'))&&wr.nibble%3===1&&wr.nibble<37)||
      (wr.chip===3&&wr.command===request.command&&wr.slot==='W'&&[28,31,34].includes(wr.nibble)),
      'undeclared K8 tetra change: '+JSON.stringify(wr));
  const last=r.traced.events.filter(e=>e.stage==='after-upper-1');
  const lastRead=last.find(e=>e.ip===0xEE&&e.nextIp!==0xE3);assert.ok(lastRead);
  same([lastRead.slot,lastRead.raw,lastRead.nextIp],['X1',b,0xF0]);
  const push=checks.exactPush(r,'after-upper-1',['P7','P8','P9','P10']);
  same(push.displaced,a);
  const lastLateRead=last.find(e=>e.ip===0xEE&&e.nextIp===0xE3);assert.ok(lastLateRead);
  same([lastLateRead.slot,lastLateRead.raw],['X',b]);
  const lastLate=last.find(e=>e.command>lastLateRead.command&&e.ip===0xE7);
  repack.exactCopy(r,lastLate,'P7',b);
  same(last.filter(e=>[0xE9,0xA3].includes(e.ip)),[],'LastX makes no E9/request');
  for(const wr of r.traced.writes.filter(w=>w.command>=middle.command&&w.before!==w.value)) {
    const i=wr.command-push.command;
    assert.ok(wr.chip===3&&((i>=0&&i<4&&wr.slot===['P7','P8','P9','P10'][i]&&
      wr.nibble%3===1&&wr.nibble<37)||(wr.command===lastLate.command&&wr.slot==='P7'&&
      wr.nibble%3===1&&wr.nibble<37)),
      'undeclared LastX tetra change: '+JSON.stringify(wr));
  }
  same(values(end),{...values(middle),P7:b,P8:zero,P9:c,P10:d});
  same(r.afterRegisters,r.beforeRegisters.map((value,i)=>i?value:w));
  same(r.after,Object.fromEntries(names.map(n=>[n,r.before[n].slice(0,2)+raw(end.ring[n])])));
  same(['X1','X','Y','Z','T'].map(n=>raw(end.ring[n])),[b,b,a,u,q]);
  same(Object.keys(end.ring).filter(n=>end.ring[n][22]===15).sort(),['V','marker']);
  const rows=repack.boundaryLosses(r);same(rows.filter(e=>e.missing.length),[]);
  const finalWords=snapshotFromRing(end.ring).words;
  const places=[...PLACES,'X1','X','Y','Z','T'];
  const live=[...finalWords,...['X1','X','Y','Z','T'].map(n=>raw(end.ring[n]))];
  const where=value=>places.filter((_,i)=>live[i]===value);
  same(where(a),['Y']);same(where(u),['Z']);same(where(q),['T']);same(where(p),['ms.Q']);
  return {prefix,boundaries:rows.length,all23HeldAtActionBoundaries:true,
    k8:{control:ctrl.command,read:read.command,saveB:copy.command,request:request.command,
      lateRead:lateRead.command,lateWrite:late.command,
      ik1306Acknowledge:ack.command,ik1306Clear:clearCommand},
    lastX:{read:lastRead.command,source:'X1',value:b,push,lateRead:lastLateRead.command,
      lateSource:'X',lateWrite:lastLate.command,lateTarget:'P7'},
    upper:[b,zero,c,d],visible:[b,b,a,u,q],other14OrdinaryProgramAndServiceHeld:true,
    pStillOnlyInQ:true,aOnlyInY:true,numericScope:'baseline fixture only',
    normalStoredBankContract:false,workingExit:false,fullK1:false};
}
function diagnostic(r) {
  const at=checks.boundary(r,'after-upper-0').command;
  return {end:values(checks.boundary(r,'done')),
    routes:r.traced.events.filter(e=>e.stage.startsWith('after-upper-')&&
      [0x9C,0xEE,0xE9,0xA3,0xE7,0xA8].includes(e.ip))
      .map(e=>({stage:e.stage,n:e.command,ip:e.ip.toString(16),slot:e.slot,
        raw:e.raw,next:e.nextIp.toString(16)})),
    changed:r.traced.writes.filter(w=>w.command>=at&&w.before!==w.value)};
}
if(require.main===module) {
  console.log('PASS keyboard surface:',JSON.stringify(surface()));
  const r=probe.run();
  try {console.log('PASS upper vacancy:',JSON.stringify(check(r)));}
  catch(error) {console.log('DIAGNOSTIC:',JSON.stringify(diagnostic(r)));throw error;}
  if(process.env.K1_UPPER_VACANCY_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check,diagnostic};
