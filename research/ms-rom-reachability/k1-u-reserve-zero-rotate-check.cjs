#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-u-reserve-zero-rotate.cjs');
const reserve=require('./k1-single-v-u-reserve-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const word=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});
const zero='000000000000',m='9990FFFFFFF0';
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();

function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}

function check(r,{beforeDropStage}={}) {
  // A passive slice can audit the exact rotation before a different closing
  // tail; it neither invents a drop action nor changes calculator state.
  if(beforeDropStage)r=prefixView(r,beforeDropStage);
  else assert.notEqual(r.options.clearMarker,false,'this audit includes marker removal');
  const prefix=reserve.check(r,'u-reserve/tail-0');
  checks.protectedFields(r,[0],['U','V','W','Q','P7','P8']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.nibble<37&&w.before!==w.value),[]);
  const [u,v,w,q,a,b]=['U','V','W','Q','P7','P8'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const begin=checks.boundary(r,'u-reserve/tail-0'),masked=checks.boundary(r,'u-reserve/tail-2');
  const rotate=checks.boundary(r,'u-reserve/tail-3'),drop=checks.boundary(r,beforeDropStage?'done':'zero-rotate/drop-t');
  const end=checks.boundary(r,'done'),allowed=new Set();
  function operation(stage,source,target,request,opcode,lateValue,lateTarget) {
    const es=r.traced.events.filter(e=>e.stage===stage);
    assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
    const reads=es.filter(e=>e.ip===0xEE);
    same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[[source,v,0xA1],['X',lateValue,0xE3]]);
    const copies=es.filter(e=>e.ip===0xE9);same(copies.length,1);
    repack.exactCopy(r,copies[0],target,v);allowed.add('3:'+copies[0].command);
    const requests=es.filter(e=>e.ip===0xA3);same(requests.length,1);const req=requests[0];same(req.slot,request);
    const expected=ringAt(r,req.command),values=[parseInt(v[2],16),opcode%16,opcode>>4];
    [28,31,34].forEach((n,j)=>{expected[request][n]=values[j];});
    same(ringAt(r,req.command+1),expected,'only three exact request tetras');
    same(r.traced.writes.filter(w=>w.command===req.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
      [28,31,34].map((n,j)=>[3,request,n,values[j]]));allowed.add('3:'+req.command);
    const lates=es.filter(e=>e.ip===0xE7);same(lates.length,1);
    repack.exactCopy(r,lates[0],lateTarget,lateValue);allowed.add('3:'+lates[0].command);
    return {gates:es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),
      read:reads[0].command,copy:copies[0].command,request:req.command,
      lateRead:reads[1].command,late:lates[0].command};
  }
  const maxes=[operation('u-reserve/tail-0','X','V','control',0x36,v,'W'),
    operation('u-reserve/tail-1','W','X1','U',0x36,v,'W')];
  same(maxes.map(x=>x.gates),[[['U',0x9E],['U',0x9E]],[['control',0x9E],['control',0x9E]]]);
  const ack3=r.traced.writes.filter(w=>w.command>=begin.command&&w.command<masked.command&&w.chip===5&&w.before!==w.value);
  same(ack3.map(w=>[w.ip,w.slot,w.nibble,w.before,w.value]),[[0xFD,'control',31,6,15]]);
  allowed.add('5:'+ack3[0].command);
  const expectedMasked=structuredClone(begin.ring);
  for(const [n,value] of Object.entries({X1:v,V:v,W:v,U:'36'+v.slice(2),
    control:'3F'+v[2]+raw(begin.ring.control).slice(3)}))word(expectedMasked,n,value);
  same(masked.ring,expectedMasked);same(marks(masked),['T','marker']);
  const clearEvents=r.traced.events.filter(e=>e.stage==='u-reserve/tail-2');
  const clears=clearEvents.filter(e=>e.ip===0xE7);same(clears.length,1);
  repack.exactCopy(r,clears[0],'X',zero);allowed.add('3:'+clears[0].command);
  // In this earlier position IK1306 continues its repeated numeric writes
  // until the rotation request. They are identities, not another clear:
  // before the primary Cx they write v, afterwards zero. Audit all of them.
  const third=r.traced.writes.filter(w=>w.command>=masked.command&&w.command<drop.command&&w.chip===5);
  const thirdGroups=new Map();
  for(const wr of third) {
    if(!thirdGroups.has(wr.command))thirdGroups.set(wr.command,[]);
    thirdGroups.get(wr.command).push(wr);allowed.add('5:'+wr.command);
  }
  for(const [command,ww] of thirdGroups) {
    if(ww[0].ip===0xFD)same(ww.map(w=>[w.ip,w.slot,w.nibble,w.before,w.value]),[[0xFD,'control',31,15,15]]);
    else same(ww.map(w=>[w.ip,w.slot,w.nibble]),Array.from({length:12},(_,j)=>[0xFF,'X',1+3*j]));
    assert.ok(ww.every(w=>w.before===w.value),'every third-chip write is idempotent');
    same(r.traced.writes.filter(w=>w.command===command),ww,'no concurrent writer in a third-chip echo/ACK command');
  }
  assert.ok(thirdGroups.size,'the repeated third-chip path was observed');
  const expectedRotate=structuredClone(masked.ring);word(expectedRotate,'X',zero);same(rotate.ring,expectedRotate);

  const rotation=operation('u-reserve/tail-3','W','X1','U',0x25,zero,'X');
  assert.ok(rotation.gates.some(([n,next])=>n==='control'&&next===0x9E));
  assert.ok(rotation.gates.every(([n,next])=>n==='control'?next===0x9E:n==='U'&&next===0x9D));
  const es=r.traced.events.filter(e=>e.stage==='u-reserve/tail-3');
  const secondary=r.traced.writes.filter(w=>w.command>=rotate.command&&w.command<drop.command&&w.chip===4);
  const acks=secondary.filter(w=>w.ip===0x27),output=secondary.filter(w=>w.ip!==0x27);
  same(acks.map(w=>[w.slot,w.nibble,w.before,w.value]),[['U',31,5,15],['U',31,15,15]]);
  assert.ok(output.length);const first=output[0].command;
  same(output.map(w=>[w.command-first,w.ip,w.slot,w.nibble]),['W','Q','P7','P8'].flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i,i===3?0x2A:0x3A,n,1+3*j])));
  same(r.traced.writes.filter(w=>w.command>=first&&w.command<first+4),output,'no concurrent output writer');
  const old=ringAt(r,first),expectedOutput=structuredClone(old);
  for(const [dst,src] of [['W','Q'],['Q','P7'],['P7','P8'],['P8','W']])word(expectedOutput,dst,raw(old[src]));
  same(ringAt(r,first+4),expectedOutput,'four exact rotated words, all 630 tetras');
  same(['W','Q','P7','P8'].map(n=>raw(expectedOutput[n])),[p,a,b,v]);
  for(const wr of secondary)allowed.add('4:'+wr.command);
  const ips='6E 5E 50 52 53 4F 24 26 28 D3 37 37 37 37 37 37 27 D4 D4 D4 D4 D4 C4 2C 3B 2B 60 37 37 37 37 27 61 3A 3A 3A 2A 39'.split(' ').map(x=>parseInt(x,16));
  const consumer=first-33,native=es.filter(e=>e.command>=consumer&&e.command<consumer+ips.length);
  same(native.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),ips.map((ip,i)=>[ip,slots[(6+i)%15]]));
  const s=native[0].otherChips[4];same([s.r[29],s.st[36],s.st[39],s.st[37],s.st[40]],[0,10,3,10,3]);
  same([raw(native[3].otherChips[4].m),raw(native[4].otherChips[4].m)],[v,p]);
  assert.ok(first+3<rotation.late,'secondary finishes first; late zero is harmless in X');
  const expectedDrop=structuredClone(rotate.ring);
  for(const [n,value] of Object.entries({U:'2F'+v.slice(2),W:p,Q:a,P7:b,P8:v}))word(expectedDrop,n,value);
  same(drop.ring,expectedDrop);same(marks(drop),['T','marker']);

  if(beforeDropStage) {
    same(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&w.before!==w.value
      &&!allowed.has(w.chip+':'+w.command)),[],'no undeclared changed tetra before the alternate closing tail');
    const rows=repack.boundaryLosses(r);same(rows.filter(x=>x.missing.length),[]);
    const stored=snapshotFromRing(end.ring).words;
    same(snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words.filter(x=>!stored.includes(x)),[u,q]);
    return {prefix,boundaries:rows.length,maxes,zero:clears[0].command,
      rotation:{...rotation,consumer,output:first},all23LiveAtEveryBoundary:true,
      uOnlyInY:true,qOnlyInZ:true,remainingMarker:'T',beforeAlternateClosingTail:true,
      additionRemovedFromUpperTail:true,fullK1:false};
  }

  const rs=r.traced.events.filter(e=>e.stage==='zero-rotate/drop-t');
  same(rs.filter(e=>[0xE9,0xA3].includes(e.ip)),[]);
  const gates=rs.filter(e=>e.ip===0x9C);same(gates.length,1);
  assert.ok(['control','U'].includes(gates[0].slot));same(gates[0].nextIp,0x9E);
  const reads=rs.filter(e=>e.ip===0xEE);
  same(reads.map(e=>[e.slot,e.raw]),[[gates[0].slot==='control'?'W':'X',gates[0].slot==='control'?p:zero],['X',w]]);
  const loads=rs.filter(e=>e.ip===0xD6);same(loads.length,1);same([loads[0].slot,raw(loads[0].m,0)],['U',w]);
  const push=checks.exactPush(r,'zero-rotate/drop-t',['X','Y','Z','T']);same(push.displaced,m);
  const late=rs.filter(e=>e.ip===0xE7&&e.command>reads[1].command);same(late.length,1);
  repack.exactCopy(r,late[0],'X',w);same(reads[1].nextIp,0xE3);
  for(const c of [push.command,push.command+1,push.command+2,push.command+3,late[0].command])allowed.add('3:'+c);
  const expectedEnd=structuredClone(drop.ring);
  for(const [n,value] of Object.entries({X:w,Y:zero,Z:u,T:q}))word(expectedEnd,n,value);
  same(end.ring,expectedEnd);same(marks(end),['marker']);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&w.before!==w.value
    &&!allowed.has(w.chip+':'+w.command)),[],'no undeclared changed tetra in the entire new tail');
  const rows=repack.boundaryLosses(r);same(rows.filter(x=>x.missing.length),[]);
  const stored=snapshotFromRing(end.ring).words;
  same(snapshotFromRing(r.traced.events.find(e=>e.ring).ring).words.filter(x=>!stored.includes(x)),[u,q]);
  same([raw(end.ring.V),raw(end.ring.P8)],[v,v]);
  return {prefix,boundaries:rows.length,maxes,zero:clears[0].command,
    thirdChipIdempotentNumericCommands:[...thirdGroups.values()].filter(ww=>ww[0].ip===0xFF).length,
    rotation:{...rotation,consumer,output:first},
    drop:{acceptedAt:gates[0].slot,read:loads[0].command,push,late:late[0].command},
    all23LiveAtEveryBoundary:true,allExtraMarkersRemoved:true,upperAInQ:true,originalPInW:true,
    VHasUpperP8Backup:true,additionRemovedFromUpperTail:true,exactNoAbsorptionRequired:true,
    uOnlyInZ:true,qOnlyInT:true,UStillRequestHeader:true,all23BackInStoredWords:false,
    universalEntryProved:false,normalExitTested:false,fullK1:false};
}

if(require.main===module) {
  const o={...probe.defaults,...JSON.parse(process.env.K1_ZERO_ROTATE_OPTIONS||'{}')};
  if(process.env.K1_ZERO_ROTATE_LARGE_V)o.values=['-1.2345678E-42','-7.654321E-23','-9.8765432E-3','-12345678'];
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS exact guarded rotation:',JSON.stringify(check(r)));
  if(process.env.K1_ZERO_ROTATE_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check};
