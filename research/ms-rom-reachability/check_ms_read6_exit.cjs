#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_read6_exit.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {checkPairedPath}=require('./check_ms_upper_read2_exit.cjs');
const {checkSuffix}=require('./check_ms_swap_handoff.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const zero='000000000000',marker='0000F0000000',guard='958912345678';
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const outputs=[[1,'U'],[6,'V'],[11,'W'],[13,'Q'],[8,'P7'],[10,'P8']];

function compactPath(es,stage,{capture=false,postMarker=false,unsafeCanonical=false,postPointer=111}={}) {
  const rows=es.filter(e=>e.stage===stage),at=rows.findIndex(e=>e.ip===0xD6),first=rows[at];
  assert.ok(first);
  const pointerRaw=raw(first.m,0);
  assert.ok([110,111].includes(postPointer));
  const entries=postMarker?{Y:'001010000000',U:'0020'+String(postPointer).padEnd(8,'0')}:{Y:'001010000000',P8:'007000000010'};
  if(unsafeCanonical)entries.P8='001010000000';
  assert.equal(pointerRaw,entries[first.slot],'one of the symbolically checked native entries');
  assert.deepEqual([first.r[29],first.r[32],first.r[35],first.r[26],first.s1],
    [13,12,Number(capture),15,6]);assert.deepEqual(first.sp,[0x2F,0xAC,0x9A]);
  const pointer=pointerRaw.startsWith('0020')?postPointer:10,index=pointer%100;
  const markers=new Set(['marker','V',...(postMarker?['X']:[])]);
  const seq=[0xD6,...Array.from({length:7-Number(pointerRaw.slice(0,3))},()=>[0x2F,0x20]).flat(),
    0x2F,0x21,0x23,0x25];
  const slot=()=>slots[(slots.indexOf(first.slot)+seq.length)%15];
  const helper=(n,load=false)=>{
    while(!markers.has(slot()))seq.push(1);
    seq.push(1,...Array(n+1).fill(2),3,4,0xBA,0xCB,0xDD,load?0xD6:0xD4);
  };
  helper(12);seq.push(0x26,0x28,0x7E,capture?0x71:0x70);
  if(capture) {
    seq.push(0xAA);while(!markers.has(slot()))seq.push(0xE5);
    seq.push(0xE5,0xE6,0xED,0xEE,0xAB,0xAD,0xA4);helper(index);
  } else {
    seq.push(0xAB,0xAD,0xA6);helper(index,true);seq.push(0xA7);
    while(!markers.has(slot()))seq.push(0xE5);
    seq.push(0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9);
  }
  const path=rows.slice(at,at+seq.length);
  assert.deepEqual(path.map(e=>[e.ip,e.slot]),seq.map((ip,i)=>[ip,slots[(slots.indexOf(first.slot)+i)%15]]),
    'every native command and physical slot matches the connected symbolic contract');
  for(const e of path)if([1,0xE5].includes(e.ip))assert.equal(e.m[22]===15,markers.has(e.slot));
  assert.deepEqual(path.filter(e=>e.ip===0xD4).map(e=>e.slot),unsafeCanonical?['Y','Q']:(capture?['P8','X1']:['P8']));
  const writtenPointer=path.find(e=>e.ip===0xD4);
  assert.equal(raw(path[path.indexOf(writtenPointer)-1].r,0),'007'+String(pointer).padStart(9,'0'));
  if(!capture) {
    const reads=path.filter(e=>e.ip===0xD6);
    assert.equal(reads[1].slot,pointer===111?'P7':'Q');
    assert.equal(raw(reads[1].m,0),pointer===111?guard:zero);
  }
  return {start:first.slot,pointer,commands:seq.length};
}

function checkCopy(r,stage,word,destination) {
  const es=r.traced.events,source=es.find(e=>e.stage===stage&&e.ip===0xEE&&e.slot==='P7');
  assert.ok(source);assert.equal(source.raw,r.before[word].slice(2));
  const at=es.findIndex(e=>e.stage===stage&&e.command>source.command&&e.ip===0xD4&&e.slot===destination);
  assert.ok(at>=0);const write=es[at],next=es[at+1];assert.equal(next.ip,0xA5);
  const expected=structuredClone(write.ring);
  for(let i=0;i<12;i++)expected[destination][3*i]=source.m[1+3*i];
  assert.deepEqual(next.ring,expected,'copy changes only twelve M1 tetras among all 630');
  const writes=r.traced.writes.filter(w=>w.command===write.command);
  assert.equal(writes.length,12);
  assert.ok(writes.every(w=>w.chip===3&&w.slot===destination&&w.nibble%3===0&&w.nibble<=33));
}

function check(r) {
  const es=r.traced.events;
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(es.every(e=>e.ip!==0xC9));
  const handoff=es.find(e=>e.stage==='prepare-zero-p8');assert.ok(handoff.ring);
  for(const word of Object.keys(r.before))assert.equal(raw(handoff.ring[word],1,14),r.before[word]);
  for(const [slot,word] of [['V','U'],['P9','V'],['X','W'],['Z','Q']])
    assert.equal(raw(handoff.ring[slot],0),r.before[word].slice(2),'lower backup survives scratch setup');
  assert.equal(raw(handoff.ring.U,0),'002011100000');
  assert.equal(raw(handoff.ring.P8,0),'007000000010');
  assert.equal(raw(handoff.ring.Y,0),'001010000000');
  assert.equal(raw(handoff.ring.W,0),marker);assert.equal(raw(handoff.ring.Q,0),zero);
  assert.ok(!es.some(e=>e.stage==='read-0'),'P0=111 is not overwritten by the old redundant fifth-word store');
  checkCopy(r,'upper-copy-fifth','P7','marker');
  const prime=es.findIndex(e=>e.stage==='upper-prime'&&e.ip===0xE7&&e.slot==='P7'&&e.nextIp===0x47);
  const guarded=checkSwapBlock(r,prime,1);
  assert.equal(guarded.body[0].raw,r.before.P7.slice(2));assert.equal(raw(guarded.body[0].r,0),guard);
  assert.equal(raw(guarded.body[0].ring.marker,0),r.before.P7.slice(2),'fifth already saved before the guard write');
  checkSuffix(r,guard,'Z',9,0x42,'X');
  const secondaryAt=es.findIndex(e=>e.stage==='upper-swap'&&e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='P7');
  assert.ok(secondaryAt>=0);const pair=es.slice(secondaryAt,secondaryAt+3),a=pair[0].otherChips[4];
  assert.deepEqual(pair.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x4E,'P7'],[0x2A,'P8'],[0x39,'P9']]);
  assert.equal(raw(a.r,0),r.before.P8.slice(2));assert.equal(raw(a.m),guard);
  const swapped=structuredClone(pair[0].ring);
  for(let i=0;i<12;i++){swapped.P7[1+3*i]=a.r[3*i];swapped.P8[1+3*i]=a.m[1+3*i];}
  assert.deepEqual(pair[2].ring,swapped);
  const swapWrites=r.traced.writes.filter(w=>w.command>=pair[0].command&&w.command<pair[2].command);
  assert.equal(swapWrites.length,24);assert.ok(swapWrites.every(w=>w.chip===4&&w.nibble%3===1&&w.nibble<=34));
  const paths=[compactPath(es,'upper-after-0',{capture:true})];
  checkCopy(r,'upper-after-0','P8','X1');
  for(let i=1;i<=3;i++) {
    const stage='upper-after-'+i;paths.push(compactPath(es,stage));
    const at=es.findIndex(e=>e.stage===stage&&e.ip===0xE7&&e.nextIp===0xA8);
    const block=checkSwapBlock(r,at,4);assert.equal(raw(block.body[0].r,0),zero);
    assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);
    assert.ok(es.filter(e=>e.stage===stage&&e.ip===0xE7).every(e=>e.slot==='X'));
  }
  checkPairedPath(es,'upper-after-4',14,'W');
  const marked=checkSwapBlock(r,es.findIndex(e=>e.stage==='upper-after-4'&&e.ip===0xE7&&e.nextIp===0xA8),4);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(marked.after.ring[n])),[marker,zero,zero,zero]);
  const post=compactPath(es,'upper-after-5',{postMarker:true});paths.push(post);
  const shifted=checkSwapBlock(r,es.findIndex(e=>e.stage==='upper-after-5'&&e.ip===0xE7&&e.nextIp===0xA8),4);
  assert.equal(raw(shifted.after.ring.Y),marker);assert.equal(raw(shifted.after.ring.Z),zero);
  const erased=checkSwapBlock(r,es.findIndex(e=>e.stage==='upper-after-6'&&e.ip===0xE7&&e.slot==='V'),1);
  assert.equal(erased.body[0].raw,marker);assert.equal(raw(erased.body[0].r,0),guard);assert.equal(erased.after.ip,0x47);
  const expected=Array(15);
  for(const [index,word] of outputs)expected[index]=r.before[word].slice(2);
  expected[0]='002011100000';expected[2]=marker;expected[3]=zero;expected[4]=guard;
  expected[5]='007'+String(post.pointer).padStart(9,'0');
  const eRead=es.find(e=>e.stage==='upper-after-4'&&e.ip===0xD6);
  expected[7]=eRead.slot==='P10'?'007000000009':'000090000000';
  expected[14]=eRead.slot==='T'?'007000000002':'000020000000';
  expected[9]=r.options.restoreLower?r.before.U.slice(2):marker;expected[12]='001010000000';
  assert.deepEqual(r.afterRegisters,expected,'all six full-word outputs and exactly the declared scratch contents');
  const afterUpper=es.find(e=>e.stage===(r.options.restoreLower?'restore-source-Сx':'done')).ring;
  const request=es.find(e=>e.stage==='upper-swap'&&e.ip===0xA2&&e.slot==='V');
  const upperMs=Object.fromEntries(Object.keys(r.before).map(n=>[n,raw(afterUpper[n],1,14)]));
  assert.ok([zero,guard].includes(upperMs.U.slice(2)));
  assert.ok([guard,r.before.P8.slice(2)].includes(upperMs.P7.slice(2)));
  assert.deepEqual(upperMs,{...r.before,U:r.before.U.slice(0,2)+upperMs.U.slice(2),
    V:r.before.V.slice(0,2)+guard,
    W:r.before.W.slice(0,2)+'1F'+request.r[27].toString(16).toUpperCase()+r.before.U.slice(5),
    Q:r.before.Q.slice(0,2)+r.before.V.slice(2),
    P7:r.before.P7.slice(0,2)+upperMs.P7.slice(2),P8:r.before.P8.slice(0,2)+guard});
  if(r.options.restoreLower) {
    assert.deepEqual(r.after,{...upperMs,...Object.fromEntries(['U','V','W','Q'].map(n=>[n,r.before[n]]))});
    for(const [key,word] of [['Сx','Q'],['/-/','W'],['6','V'],['1','U']]) {
      const at=es.findIndex(e=>e.stage==='restore-lower-'+key+'/shifted-swap'&&e.ip===0xE7&&e.slot==='U');
      const block=checkSwapBlock(r,at,4);assert.equal(raw(block.body[0].r,0),r.before[word].slice(2));
    }
  } else assert.deepEqual(r.after,upperMs);
  const done=es.findLast(e=>e.ring).ring;
  for(const n of ['X','Y','Z','T'])assert.equal(raw(done[n]),zero);
  for(const n of Object.keys(r.before))assert.notEqual(done[n][22],15,'no internal marker remains');
  const changed=r.traced.writes.filter(w=>Object.hasOwn(r.before,w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(changed.every(w=>!['P9','P10'].includes(w.slot)&&w.nibble<=34),
    'last two Ms words and every Ms service tetra unchanged throughout');
  const captured=es.find(e=>e.stage==='upper-after-1').command;
  const restored=es.find(e=>e.stage==='restore-source-Сx')?.command??Infinity;
  assert.ok(changed.filter(w=>w.command>=captured&&w.command<restored).every(w=>['U','V','P7'].includes(w.slot)));
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),expected);assert.deepEqual(program(r.calc),r.beforeProgram);
  r.calc.pressSequence(['В/О','С/П']).runFrames(12);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');assert.equal(r.calc.programCounter(),'05');
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),expected);assert.deepEqual(program(r.calc),r.beforeProgram);
  return paths;
}

function main() {
  const complex={stress:true,restoreLower:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
    upperValues:['6.5432109E-23','-8.7654321E-17','333','444']};
  const cases=[...[0,1,2].map(phaseOffset=>({...complex,phaseOffset})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true,restoreLower:true,upperValues:['-1E-99','0','333','444']})),
    ...[0,1,2].map(phaseOffset=>({phaseOffset,stress:true})),
    {stress:true,restoreLower:true,upperValues:['0','0','333','444']},
    {stress:true,restoreLower:true,upperValues:['0','222','333','444']},
    {stress:true,restoreLower:true,upperValues:['-9.8765432E99','1.2345678E99','333','444']},
    {...complex,settleFrames:12,markerFrames:8}];
  let firstDigest;const captures=new Set(),postEntries=new Set();
  for(const o of cases) {
    const r=p.run(o);firstDigest??=digest(r.calc);const paths=check(r);
    captures.add(paths[0].start);postEntries.add(paths.at(-1).start);
    console.log('PASS:',JSON.stringify(o),'six exact backups; connected ROM paths; no hidden/visible marker; arithmetic and preserved program = 5.');
  }
  assert.deepEqual([...captures].sort(),['P8','Y']);assert.deepEqual([...postEntries].sort(),['U','Y']);
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);
  console.log('PASS: observed/unobserved complete core state:',firstDigest);
  const bad=p.run({...complex,phaseOffset:0,restoreLower:false,canonicalCaptureMirror:true});
  const stage=bad.traced.events.filter(e=>e.stage==='upper-after-0');
  const first=stage.find(e=>e.ip===0xD6);
  assert.equal(first.slot,'P8');assert.equal(raw(first.m,0),'001010000000');
  compactPath(bad.traced.events,'upper-after-0',{capture:true,unsafeCanonical:true});
  assert.equal(stage.find(e=>e.ip===0xEE&&e.command>first.command).slot,'X');
  assert.deepEqual(stage.filter(e=>e.ip===0xD4).map(e=>e.slot),['Y','Q']);
  assert.notEqual(bad.afterRegisters[10],bad.before.P8.slice(2));assert.notEqual(bad.afterRegisters[3],zero);
  console.log('PASS: negative control: canonical 10 in both pointers selects the real marker; stores into P3, not A, and breaks cleanup.');
  console.log('LIMIT: P3=0 and the existing lower-reader domain (nonnegative initial U exponent). Ms P7/P8 not restored; last two words not read. NOT K1.');
}
if(require.main===module)main();
module.exports={check,compactPath};
