#!/usr/bin/env node
'use strict';
// Native, lifetime-scheduled six-word reader with complete Ms restoration.
// This is a conditional readout, not the historical eight-word K1 exchange.
const assert=require('node:assert/strict');
const p=require('./probe_ms_read6_roundtrip.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkOne,checkMiddle}=require('./check_ms_zero_reuse.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const zero='000000000000',marker='0000F0000000';
const names=['U','V','W','Q','P7','P8','P9','P10'];
const upper=names.slice(4),lower=names.slice(0,4);
const m1=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
const stage=(r,label)=>r.traced.events.filter(e=>e.stage===label);
const at=(r,label)=>stage(r,label).find(e=>e.ring);
const ringAt=(r,label)=>at(r,label).ring;
const ms=(ring,which=names)=>Object.fromEntries(which.map(n=>[n,raw(ring[n],1,14)]));

function checkLowerPush(r,prefix,source) {
  const es=r.traced.events,where=es.findIndex(e=>e.stage===prefix+'shifted-swap'&&e.ip===0xE7&&e.slot==='U');
  assert.ok(where>=0);const block=checkSwapBlock(r,where,4);
  assert.deepEqual(block.body.map(e=>e.slot),lower);assert.equal(raw(block.body[0].r,0),source);
  const loadAt=es.findLastIndex((e,i)=>i<where&&e.ip===0xD6);
  assert.equal(raw(es[loadAt].m,0),source);
  assert.deepEqual(es.slice(loadAt,where+6).map(e=>[e.ip,e.slot]),
    [[0xD6,'control'],[0xA7,'X1'],[0xE5,'X'],[0xE5,'Y'],[0xE6,'Z'],[0xE8,'T'],
      [0xE7,'U'],[0xA8,'V'],[0xA8,'W'],[0xA8,'Q'],[0xA9,'P7'],[0xAC,'P8']]);
  return block;
}

function checkBridge(r,prefix,next,final=false) {
  const begin=at(r,prefix+'save-q-backup'),readLabel=prefix+(final?'final-copy-8-4':'put-v-in-u/clear-before');
  const read=at(r,readLabel),end=at(r,next),v=r.before.V.slice(2),q=r.before.Q.slice(2);
  assert.equal(raw(begin.ring.Q),v,'V survived the preceding upper operation in Ms Q');
  assert.equal(raw(begin.ring.Q,0),q,'original Q is still in ordinary P3');
  assert.equal(raw(read.ring.control,0),v,'the secondary reader recovered Ms Q in ordinary P9');
  assert.equal(raw(read.ring.T,0),q,'Q backup was parked in E while P3 was zero');
  assert.equal(raw(read.ring.Q,0),zero);
  const visible=['X','Y','Z','T'];
  const firstRows=stage(r,prefix+'read-q/post-swap-0');
  const liftAt=firstRows.findIndex(e=>e.ip===0xE7&&e.slot==='X'&&e.nextIp===0xA8);assert.ok(liftAt>=0);
  const firstLift=firstRows.slice(liftAt,liftAt+5),initial=firstLift[0].ring,shifted=structuredClone(initial);
  assert.deepEqual(firstLift.map(e=>[e.ip,e.slot]),[[0xE7,'X'],[0xA8,'Y'],[0xA8,'Z'],[0xA8,'T'],[0xA9,'U']]);
  assert.equal(raw(firstLift[0].r,0),zero);assert.equal(raw(initial.X),v);assert.equal(raw(initial.Y),v);
  const overlap=firstLift[1].otherChips[4].ip===0x4E&&firstLift[1].otherChips[4].slot==='X';
  const out=overlap?[v,zero,v,raw(initial.Z)]:[zero,v,v,raw(initial.Z)];
  for(let n=0;n<4;n++)for(let j=0;j<12;j++)shifted[visible[n]][1+3*j]=parseInt(out[n][11-j],16);
  if(overlap) {
    assert.deepEqual([firstLift[2].otherChips[4].ip,firstLift[2].otherChips[4].slot],[0x2A,'Y']);
    assert.equal(raw(firstLift[1].otherChips[4].r,0),v);
  }
  assert.deepEqual(firstLift[4].ring,shifted,'all 630 tetras match the zero lift with or without the last secondary X/Y output');
  const mixed=r.traced.writes.filter(w=>w.command>=firstLift[0].command&&w.command<firstLift[4].command);
  assert.equal(mixed.length,overlap?72:48);
  assert.equal(mixed.filter(w=>w.chip===3).length,48);
  assert.ok(mixed.every(w=>w.nibble%3===1&&w.nibble<=34&&(w.chip===3?visible.includes(w.slot):w.chip===4&&['X','Y'].includes(w.slot))));
  const secondAt=r.traced.events.findIndex(e=>e.stage===prefix+'read-q/post-swap-1'&&e.ip===0xE7&&e.slot==='X'&&e.nextIp===0xA8);
  const secondLift=checkSwapBlock(r,secondAt,4);
  assert.deepEqual(visible.map(n=>raw(secondLift.body[0].ring[n])),out);
  assert.equal(raw(secondLift.body[0].r,0),zero);assert.equal(raw(secondLift.after.ring.T),v);
  const beforeRotations=ringAt(r,prefix+'read-q/post-swap-2');
  assert.equal(raw(beforeRotations.T),v,'T retains V after either final secondary-output/zero-lift ordering');
  for(let i=2;i<=4;i++) {
    const label=prefix+'read-q/post-swap-'+i,rs=stage(r,label);
    const rotationAt=rs.findIndex(e=>e.otherChips?.[4].ip===0x3A&&e.otherChips[4].slot==='X');assert.ok(rotationAt>=0);
    const block=rs.slice(rotationAt,rotationAt+5),original=block[0].ring,rotated=structuredClone(original);
    assert.deepEqual(block.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
      [[0x3A,'X'],[0x3A,'Y'],[0x3A,'Z'],[0x2A,'T'],[0x39,'U']]);
    for(let n=0;n<4;n++)for(let j=0;j<12;j++)rotated[visible[n]][1+3*j]=original[visible[(n+1)%4]][1+3*j];
    assert.deepEqual(block[4].ring,rotated,'visible rotation changes exactly 48 of all 630 tetras');
    const writes=r.traced.writes.filter(w=>w.command>=block[0].command&&w.command<block[4].command);
    assert.equal(writes.length,48);assert.ok(writes.every(w=>w.chip===4&&visible.includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
    const after=ringAt(r,prefix+'read-q/'+(i===4?'save':'post-swap-'+(i+1)));
    assert.deepEqual(visible.map(n=>raw(after[n])),visible.map(n=>raw(rotated[n])),'formatter preserves the visible rotation result');
  }
  assert.deepEqual(ms(read.ring,upper),ms(begin.ring,upper));
  const altered=r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&names.includes(w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(altered.every(w=>lower.includes(w.slot)&&w.nibble<=34),'bridge never changes any upper Ms word or service field');
  for(const [slot,original] of [['V','W'],['marker','U'],['X','P7'],['X1','P8']]) {
    assert.equal(raw(read.ring[slot],0),r.before[original].slice(2));
    assert.equal(raw(end.ring[slot],0),r.before[original].slice(2),'retained original '+original);
  }
  if(final) {
    for(const [key,word] of [['7','Q'],['6','W'],['5','V'],['4','U']])checkLowerPush(r,prefix+'restore-'+key+'/',r.before[word].slice(2));
  } else {
    checkLowerPush(r,prefix+'put-v-in-u/',v);checkLowerPush(r,prefix+'move-v-to-v/',zero);
    assert.equal(raw(end.ring.U),zero);assert.equal(raw(end.ring.V),v,'V is ready for the next upper operation');
    assert.equal(raw(end.ring.Q,0),q,'Q is returned to P3 before E is reused');
  }
  return overlap;
}

function check(r) {
  const read=ringAt(r,'relocate-8-9');
  for(const [reg,word] of [[1,'U'],[6,'V'],[11,'W'],[13,'Q'],[8,'P7'],[10,'P8']])
    assert.equal(raw(read[m1[reg]],0),r.before[word].slice(2),'read-six handoff output '+word);
  assert.deepEqual(ms(read,lower),Object.fromEntries(lower.map(n=>[n,r.before[n]])));
  for(const n of upper.slice(2))assert.equal(raw(read[n],1,14),r.before[n]);
  const first=ringAt(r,'sixth-to-top/prepare-zero-p8');
  for(const [reg,word] of [[1,'W'],[3,'Q'],[8,'U'],[11,'P7'],[10,'P8']])
    assert.equal(raw(first[m1[reg]],0),r.before[word].slice(2),'initial lifetime allocation '+word);
  const a=checkOne(r,'sixth-to-top/',first,ringAt(r,'bridge-first/save-q-backup'),r.before.P8.slice(2),{keepP8:true});
  const overlapA=checkBridge(r,'bridge-first/','sixth-to-second/zero-p0');
  const middle=checkMiddle(r,r.before.P8.slice(2),{keepP8:true,doneLabel:'bridge-second/save-q-backup'});
  const overlapMiddle=checkBridge(r,'bridge-second/','fifth-to-top/zero-p0');
  const b=checkOne(r,'fifth-to-top/',ringAt(r,'fifth-to-top/prepare-zero-p8'),
    ringAt(r,'restore-all-lower/save-q-backup'),r.before.P7.slice(2),{keepP8:true,sourceIndex:11});
  const overlapB=checkBridge(r,'restore-all-lower/','done',true);
  assert.deepEqual(r.after,r.before,'all 8 full 14-tetra Ms words are restored');
  const post=b.post==='U'?'007000000000':'000070000000';
  assert.deepEqual(r.afterRegisters,[zero,r.before.W.slice(2),marker,zero,
    ...lower.map(n=>r.before[n].slice(2)),r.before.U.slice(2),r.before.U.slice(2),
    r.before.P8.slice(2),r.before.P7.slice(2),post,'007000000011',r.before.Q.slice(2)],
    'all 15 ordinary registers, including six numeric readouts and explicit scratch');
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(r.traced.events.every(e=>e.ip!==0xC9));
  const changed=r.traced.writes.filter(w=>names.includes(w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>w.nibble<=34),'all Ms service fields remain unchanged even temporarily');
  const afterRelocation=at(r,'sixth-to-top/zero-p0').command;
  const retained=r.traced.writes.filter(w=>w.command>=afterRelocation&&['V','marker','X','X1'].includes(w.slot)&&
    w.nibble%3===0&&w.nibble<=33&&w.before!==w.value);
  assert.deepEqual(retained,[],'ordinary P1/P8/B/A copies survive every later scratch setup, bridge and writer');
  const done=ringAt(r,'done');
  for(const n of ['X','Y','Z','T'])assert.equal(raw(done[n]),zero);
  for(const n of names)assert.notEqual(done[n][22],15,'no false Ms marker at final return');
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');assert.deepEqual(fullMsPages(r.calc),r.before);
  assert.deepEqual(registers(r.calc),r.afterRegisters);assert.deepEqual(program(r.calc),r.beforeProgram);
  r.calc.pressSequence(['В/О','С/П']).runFrames(12);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');assert.equal(r.calc.programCounter(),'05');
  assert.deepEqual(fullMsPages(r.calc),r.before);assert.deepEqual(registers(r.calc),r.afterRegisters);assert.deepEqual(program(r.calc),r.beforeProgram);
  return [a,middle,b].map((path,i)=>({...path,overlap:[overlapA,overlapMiddle,overlapB][i]}));
}

function checkNegative(r,timing=false) {
  const lost=timing?zero:'958912345678';
  assert.deepEqual(r.after,{...r.before,V:r.before.V.slice(0,2)+lost});
  assert.equal(r.afterRegisters[5],lost);assert.deepEqual(r.afterProgram,r.beforeProgram);
  for(const [reg,word] of [[4,'U'],[6,'W'],[7,'Q'],[11,'P7'],[10,'P8']])assert.equal(r.afterRegisters[reg],r.before[word].slice(2));
  for(const n of ['X','Y','Z','T'])assert.equal(raw(ringAt(r,'done')[n]),zero);
  if(timing) {
    const prefix='bridge-first/read-q/',v=r.before.V.slice(2);
    const source=stage(r,prefix+'shifted-swap').find(e=>e.otherChips?.[4].ip===0x53&&e.otherChips[4].slot==='W');
    assert.ok(source);assert.equal(raw(source.otherChips[4].m),v,'ROM reader got the right source; its old exit lost it');
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(ringAt(r,prefix+'post-swap-2')[n])),[zero,zero,v,v]);
    assert.deepEqual(['X','Y','Z','T'].map(n=>raw(ringAt(r,prefix+'save')[n])),[zero,v,v,zero]);
    const save=stage(r,prefix+'save').find(e=>e.ip===0xD4&&e.slot==='control');
    assert.ok(save);assert.equal(raw(save.r,0),zero,'ordinary P9 receives zero, not the source still in Y/Z');
  }
}

function releaseObservation(r) {
  // These are host-side logs, never emulated state. A completed test can be
  // several GB with full secondary-chip snapshots. Explicitly discard them
  // before constructing the next native run, even if V8 keeps this loop's
  // previous result binding alive during the next initializer.
  r.traced.events.length=0;r.traced.writes.length=0;
}

function main() {
  const complex={stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
    fullUpper:['3.2109876E-19','-4.3210987E31','1.2345678E-42','-9.8765432E17']};
  const cases=[...[0,1,2].map(phaseOffset=>({...complex,phaseOffset})),
    {...complex,fullUpper:['0','-1E-99','1.2345678E-42','-9.8765432E17']},
    {...complex,phaseOffset:1,fullUpper:['1.2345678E99','0','1.2345678E-42','-9.8765432E17']},
    {...complex,settleFrames:12,markerFrames:8},
    {stress:true,values:['0','0','0','0'],upperValues:['0','0','333','444']},
    {...complex,phaseOffset:2,values:['-1E-99','-1.2345678E-42','-9.8765432E99','-7.654321E23']}];
  const from=Number(process.env.MS_ROUND_FROM??0),limit=Number(process.env.MS_ROUND_CASES??cases.length);
  const controlsOnly=process.env.MS_ROUND_CONTROLS_ONLY==='1';
  let firstDigest=controlsOnly?process.env.MS_ROUND_EXPECTED_DIGEST:undefined;
  if(controlsOnly)assert.match(firstDigest??'',/^[0-9a-f]{64}$/,'controls-only mode requires the observed first-case digest');
  const pushes=new Set(),posts=new Set(),zeros=new Set(),overlaps=new Set();
  for(const o of (controlsOnly?[]:cases.slice(from,from+limit))) {
    const first=firstDigest===undefined;
    const r=p.run(o);firstDigest??=digest(r.calc);
    for(const path of check(r)){if(path.push)pushes.add(path.push);posts.add(path.post);path.zeros.forEach(x=>zeros.add(x));overlaps.add(path.overlap);}
    console.log('PASS roundtrip:',JSON.stringify(o),'six words -> P4/P5/P6/P7/B/A; all 8 complete Ms words restored; exact connected transfers, declared 15-register state; arithmetic/program = 5.');
    if(first)console.log('FIRST_OBSERVED_DIGEST',firstDigest);
    releaseObservation(r);
  }
  if(!controlsOnly) {
    console.log('COVERAGE',JSON.stringify({from,count:Math.min(limit,cases.length-from),pushes:[...pushes].sort(),posts:[...posts].sort(),zeros:[...zeros].sort(),overlaps:[...overlaps].sort()}));
    if(from||limit<cases.length)return;
    assert.deepEqual([...pushes].sort(),['P9','Z']);assert.deepEqual([...posts].sort(),['U','Y']);assert.deepEqual([...zeros].sort(),['P8','Y']);
    assert.deepEqual([...overlaps].sort(),[false,true]);
  }
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS observed/unobserved whole core:',firstDigest);
  const repeated=p.runPrepared(plain,{...cases[0],phaseOffset:1});check(repeated);
  console.log('PASS repeat of the complete read/restore without reset, fixture setup or ordinary-register reseeding.');
  releaseObservation(repeated);
  const missed=p.run({...complex,skipBridges:true});
  checkNegative(missed);
  console.log('PASS negative control: omitting the two V bridges loses old V, despite five correct readouts, restored upper words, intact program and zero display.');
  releaseObservation(missed);
  const stale=p.run({...complex,settleFrames:12,markerFrames:8,legacyBridgeReturn:true});checkNegative(stale,true);
  console.log('PASS negative control: old one-rotation bridge return selects Y=0 after the real W read; the three-rotation replacement selects the source retained in T.');
  releaseObservation(stale);
  console.log('LIMIT: conditional six-numerical-word reader/restorer, not eight-word K1; P9/P10 not read; original ordinary register values not retained; existing nonnegative-U-exponent entry domain applies.');
}
if(require.main===module)main();
module.exports={check,checkBridge,checkLowerPush,checkNegative};
