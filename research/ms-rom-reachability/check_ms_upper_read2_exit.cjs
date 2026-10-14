#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_read2_exit.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const marker='0000F0000000',eraser='958912345678',zero='000000000000';
function checkPairedPath(es,stage,carrier,sourceSlot) {
  const rows=es.filter(e=>e.stage===stage),at=rows.findIndex(e=>e.ip===0xD6),first=rows[at];
  assert.ok(first);
  const pointerRaw=raw(first.m,0),normalized=pointerRaw.startsWith('007');
  const pointer=normalized?Number(pointerRaw.slice(-2)):Number(pointerRaw[4]);
  assert.deepEqual([first.r[29],first.r[32],first.r[35],first.r[26],first.s1],
    [carrier+1,carrier,0,15,6],'native entry matches symbolic premises');
  assert.deepEqual(first.sp,[0x2F,0xAC,0x9A]);
  const names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  const seq=[0xD6,...Array.from({length:normalized?0:7},()=>[0x2F,0x20]).flat(),0x2F,0x21,0x23,0x25];
  const slot=()=>names[(names.indexOf(first.slot)+seq.length)%15];
  const helper=(index,load)=>{
    while(!['marker','V'].includes(slot()))seq.push(1);
    seq.push(1,...Array(index+1).fill(2),3,4,0xBA,0xCB,0xDD,load?0xD6:0xD4);
  };
  helper(carrier,false);seq.push(0x26,0x28,0x7E,0x70,0xAB,0xAD,0xA6);helper(pointer,true);
  assert.equal(names[(names.indexOf(first.slot)+seq.length-1)%15],sourceSlot);
  seq.push(0xA7);while(slot()!=='marker')seq.push(0xE5);
  seq.push(0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9);
  const path=rows.slice(at,at+seq.length);
  assert.deepEqual(path.map(e=>[e.ip,e.slot]),seq.map((ip,i)=>[ip,names[(names.indexOf(first.slot)+i)%15]]),
    'every connected command and physical slot matches the symbolic route');
  for(const e of path)if([1,0xE5].includes(e.ip))
    assert.equal(e.m[22]===15,['V','marker'].includes(e.slot));
  return {slot:first.slot,pointer,normalized,commands:seq.length};
}
function check(r,{upperP8=r.before.P7.slice(2)}={}) {
  const es=r.traced.events;
  assert.equal(r.beforeRegisters[6],'007000000010');
  assert.equal(r.beforeRegisters[13],'000030000000');
  assert.equal(r.beforeRegisters[1],'002011100000');
  assert.equal(r.afterRegisters[0],r.before.P8.slice(2),'sixth word -> ordinary P0');
  assert.equal(r.afterRegisters[8],r.before.P7.slice(2),'fifth word -> ordinary P8');
  for(let i=0;i<15;i++)if(![0,5,6,7,8,9,13,14].includes(i))
    assert.equal(r.afterRegisters[i],r.beforeRegisters[i],'not an output or protocol scratch: P'+i);
  assert.equal(r.afterRegisters[5],'007000000000');
  assert.equal(r.afterRegisters[9],marker);
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(e=>e.ip!==0xC9));
  const request=es.find(e=>e.stage==='upper-swap'&&e.ip===0xA2&&e.slot==='V');
  assert.ok(request);
  assert.ok([zero,eraser].includes(r.after.U.slice(2)));
  assert.deepEqual(r.after,{...r.before,
    U:r.before.U.slice(0,2)+r.after.U.slice(2),V:r.before.V.slice(0,2)+eraser,
    W:r.before.W.slice(0,2)+'1F'+request.r[27].toString(16).toUpperCase()+r.before.U.slice(5),
    Q:r.before.Q.slice(0,2)+r.before.V.slice(2),
    P7:r.before.P7.slice(0,2)+r.before.P8.slice(2),P8:r.before.P8.slice(0,2)+upperP8});
  for(let i=1;i<=3;i++) {
    const stage='upper-after-'+i;
    checkPairedPath(es,stage,13,'Q');
    const reads=es.filter(e=>e.stage===stage&&e.ip===0xD6);
    assert.equal(reads.length,2);assert.equal(reads[1].slot,'Q');
    assert.equal(raw(reads[1].m,0),zero,'compensated indirect recall selects ordinary P3');
    const at=es.findIndex(e=>e.stage===stage&&e.ip===0xE7&&e.nextIp===0xA8);
    const block=checkSwapBlock(r,at,4);
    assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);
    assert.equal(raw(block.body[0].r,0),zero);
    assert.ok(es.filter(e=>e.stage===stage&&e.ip===0xE7).every(e=>e.slot==='X'));
  }
  checkPairedPath(es,'upper-after-4',14,'W');
  const markerAt=es.findIndex(e=>e.stage==='upper-after-4'&&e.ip===0xE7&&e.nextIp===0xA8);
  const marked=checkSwapBlock(r,markerAt,4);
  assert.equal(raw(marked.body[0].r,0),marker);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(marked.after.ring[n])),[marker,zero,zero,zero]);
  const followAt=es.findIndex(e=>e.stage==='upper-after-5'&&e.ip===0xE7&&e.nextIp===0xA8);
  const followed=checkSwapBlock(r,followAt,4);
  assert.ok([zero,eraser].includes(raw(followed.body[0].r,0)));
  assert.equal(raw(followed.after.ring.Y),marker);assert.equal(raw(followed.after.ring.Z),zero);
  const eraseAt=es.findIndex(e=>e.stage==='upper-after-6'&&e.ip===0xE7&&e.slot==='V');
  assert.ok(eraseAt>followAt);
  const erased=checkSwapBlock(r,eraseAt,1);
  assert.equal(erased.body[0].raw,marker);assert.equal(raw(erased.body[0].r,0),eraser);
  assert.equal(erased.after.ip,0x47);assert.equal(raw(erased.after.ring.V),eraser);
  const done=es.findLast(e=>e.ring).ring;
  for(const n of ['X','Y','Z','T'])assert.equal(raw(done[n]),zero);
  for(const n of Object.keys(r.before))assert.notEqual(done[n][22],15,'no false marker remains in Ms: '+n);
  const changed=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>!['P9','P10'].includes(w.slot)&&w.nibble<=34));
  const afterSwap=es.find(e=>e.stage==='upper-after-0').command;
  assert.ok(changed.filter(w=>w.command>=afterSwap).every(w=>['U','V'].includes(w.slot)),
    'capture and marker removal change no other Ms numeric word or service tetra');
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(r.calc.displayText(),'5,');aligned(r.calc);
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
  r.calc.pressSequence(['В/О','С/П']).runFrames(12);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');assert.equal(r.calc.programCounter(),'05');
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}
function main() {
  const complex={stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
    upperValues:['6.5432109E-23','-8.7654321E-17','333','444']};
  const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset,...complex})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true})),
    {...complex,settleFrames:12,markerFrames:8},
    {stress:true,upperValues:['0','222','333','444']}];
  let firstDigest;
  for(const o of cases) {
    const r=p.run(o);firstDigest??=digest(r.calc);check(r);
    console.log('PASS:',JSON.stringify(o),'two upper words saved, V marker removed; arithmetic and preserved program both return 5.');
  }
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);
  console.log('PASS: observed/unobserved complete core state:',firstDigest);
  const bad=p.run({...complex,zeroLoads:0});
  assert.ok(bad.traced.events.some(e=>e.ip===0x9C&&e.slot==='Z'&&e.nextIp===0x9E),
    'a negative exponent beside the visible marker is misread as control');
  assert.equal(raw(bad.traced.events.findLast(e=>e.ring).ring.T),marker,'visible marker remains');
  assert.ok(bad.traced.events.some(e=>e.stage==='upper-after-3'&&e.ip===0xE7&&e.slot==='P7'&&e.nextIp===0xA8));
  for(const word of ['P7','P8','P9'])assert.equal(bad.after[word].slice(2),bad.beforeRegisters[11],
    'unintended stack lifts overwrite upper Ms with ordinary B');
  assert.equal(bad.afterRegisters[0],bad.before.P8.slice(2));assert.equal(bad.afterRegisters[8],bad.before.P7.slice(2));
  bad.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);
  assert.equal(bad.calc.displayText(),'5,','arithmetic alone would be a false positive');
  console.log('PASS: negative control without zero recalls accepts Z as control and corrupts upper Ms, despite correct backups and arithmetic=5.');
  const lost=p.run({stress:true,upperValues:['-1E-99','0','333','444']});
  assert.equal(lost.before.P7.slice(2),zero);assert.equal(lost.before.P8.slice(2),'901910000000');
  const overwrite=lost.traced.events.find(e=>e.stage==='upper-swap'&&e.ip===0xE7&&e.slot==='P7'&&e.nextIp===0x47);
  assert.ok(overwrite);assert.equal(overwrite.raw,lost.before.P8.slice(2));assert.equal(raw(overwrite.r,0),zero);
  assert.equal(raw(overwrite.ring.P8),zero);
  assert.equal(lost.afterRegisters[0],zero);assert.equal(lost.after.P7.slice(2),zero);assert.equal(lost.after.P8.slice(2),zero);
  console.log('PASS: boundary counterexample: old fifth=0 and sixth=-1E-99 loses sixth during the PRECEDING swap formatter, before cleanup starts.');
  console.log('CONDITIONAL: P3=0, prepared pointer pairs, tested fixtures. Prior swap has a zero-fifth counterexample. Ms NOT restored; NOT a six-word composition or full K1.');
}
if(require.main===module)main();
module.exports={check,checkPairedPath};
