#!/usr/bin/env node
'use strict';
// Native integration of guarded rotations and the compensated BC reader.
// All four upper sources are independently seeded by keys, including P9/P10.
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_read4.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkRotation}=require('./check_ms_upper_write.cjs');
const {compactPath}=require('./check_ms_read6_exit.cjs');
const {checkPairedPath}=require('./check_ms_upper_read2_exit.cjs');
const {checkLowerPush}=require('./check_ms_read6_roundtrip.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const names=['U','V','W','Q','P7','P8','P9','P10'],upper=names.slice(4);
const m1=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
const zero='000000000000',marker='0000F0000000',guard='958912345678';
const stage=(r,label)=>r.traced.events.filter(e=>e.stage===label);
const at=(r,label)=>stage(r,label).find(e=>e.ring);
const nums=ring=>upper.map(n=>raw(ring[n]));

function checkCopy(r,label,source,destination) {
  const es=r.traced.events,read=es.find(e=>e.stage===label&&e.ip===0xEE&&e.slot==='P7');
  assert.ok(read);assert.equal(read.raw,source,'the live M2 source is the intended original word');
  const index=es.findIndex(e=>e.stage===label&&e.command>read.command&&e.ip===0xD4&&e.slot===destination);
  assert.ok(index>=0);const write=es[index],next=es[index+1];
  // D4 begins with a one-tetra-rotated internal A; compare the actual
  // emitted M1 result below, not A in the source's display orientation.
  assert.equal(next.ip,0xA5);
  const expected=structuredClone(write.ring);
  for(let j=0;j<12;j++)expected[destination][3*j]=read.m[1+3*j];
  assert.deepEqual(next.ring,expected,'copy writes exactly 12 M1 tetras among all 630 ring tetras');
  const writes=r.traced.writes.filter(w=>w.command===write.command);
  assert.equal(writes.length,12);
  assert.ok(writes.every(w=>w.chip===3&&w.slot===destination&&w.nibble%3===0&&w.nibble<=33));
}

function checkExit(r,prefix,{postPointer=111}={}) {
  const es=r.traced.events;
  for(let i=1;i<=3;i++) {
    const label=prefix+'upper-after-'+i;compactPath(es,label);
    const block=checkSwapBlock(r,es.findIndex(e=>e.stage===label&&e.ip===0xE7&&e.nextIp===0xA8),4);
    assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);
    assert.equal(raw(block.body[0].r,0),zero);
    assert.ok(stage(r,label).filter(e=>e.ip===0xE7).every(e=>e.slot==='X'));
  }
  checkPairedPath(es,prefix+'upper-after-4',14,'W');
  const marked=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'upper-after-4'&&e.ip===0xE7&&e.nextIp===0xA8),4);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(marked.after.ring[n])),[marker,zero,zero,zero]);
  const post=compactPath(es,prefix+'upper-after-5',{postMarker:true,postPointer});
  const shifted=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'upper-after-5'&&e.ip===0xE7&&e.nextIp===0xA8),4);
  assert.equal(raw(shifted.after.ring.Y),marker);assert.equal(raw(shifted.after.ring.Z),zero);
  const erased=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'upper-after-6'&&e.ip===0xE7&&e.slot==='V'),1);
  assert.equal(erased.body[0].raw,marker);assert.equal(raw(erased.body[0].r,0),guard);
  assert.equal(erased.after.ip,0x47);
  return post;
}

function ordinaryChecks(r) {
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(r.traced.events.every(e=>e.ip!==0xC9));
  assert.ok(r.traced.writes.every(w=>w.chip!==3||w.ip!==0xC9),'no C9 write, including outside fully logged stages');
  const done=at(r,'done').ring;
  for(const n of ['X','Y','Z','T'])assert.equal(raw(done[n]),zero);
  for(const n of names) {
    assert.equal(r.after[n].slice(0,2),r.before[n].slice(0,2));
    assert.notEqual(done[n][22],15,'no hidden Ms marker remains');
  }
  assert.ok(r.traced.writes.filter(w=>names.includes(w.slot)&&w.nibble%3===1&&w.value!==w.before)
    .every(w=>w.nibble<=34),'no Ms service field is changed, even temporarily');
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
  r.calc.pressSequence(['В/О','С/П']).runFrames(12);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');assert.equal(r.calc.programCounter(),'05');
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),r.afterRegisters);
  assert.deepEqual(program(r.calc),r.beforeProgram);
}

function check(r) {
  assert.ok(!r.options.pairOnly&&!r.options.skipZeroU);
  if(r.options.initialU!==undefined) {
    assert.equal(r.before.U.slice(2),r.beforeRegisters[9],'native negative-U fixture push retained the exact literal source');
    if(r.options.initialU.includes('E-'))assert.equal(r.before.U[2],'9','the extended entry was actually exercised with a negative exponent');
  }
  const original=upper.map(n=>r.before[n].slice(2)),paths=[];
  const nextLabels=['save-fifth','save-seventh','done'];
  for(let i=0;i<3;i++) {
    const prefix='read-'+i+'/',begin=at(r,prefix+'prepare-zero-p8'),end=at(r,nextLabels[i]);
    const entryUpper=nums(begin.ring);
    assert.deepEqual(entryUpper.slice(1),[...original.slice(i+1),...Array(i).fill(guard)],
      'the remaining unread originals survive every re-entry and scratch setup');
    if(i===0) {
      assert.equal(entryUpper[0],original[0]);
      checkCopy(r,prefix+'upper-copy-fifth',original[0],'marker');
    } else {
      assert.ok([guard,original[i]].includes(entryUpper[0]));
      assert.equal(stage(r,prefix+'upper-copy-fifth').length,0);
    }
    if(i||r.options.clearInitialU) {
      const block=checkLowerPush(r,prefix+'zero-u/',zero);
      const expected=structuredClone(block.body[0].ring);
      for(let n=0;n<4;n++)for(let j=0;j<12;j++)
        expected[names[n]][1+3*j]=n?block.body[0].ring[names[n-1]][1+3*j]:0;
      assert.deepEqual(block.after.ring,expected,'the inter-pass zero push changes only lower numeric Ms');
      assert.equal(raw(begin.ring.U),zero,'re-entry starts with a nonnegative-exponent U');
    }
    const primeIndex=r.traced.events.findIndex(e=>e.stage===prefix+'upper-prime'&&e.ip===0xE7&&e.slot==='P7');
    const prime=checkSwapBlock(r,primeIndex,1);
    assert.equal(raw(prime.body[0].r,0),guard);
    assert.deepEqual(nums(prime.after.ring),[guard,...entryUpper.slice(1)]);
    if(i===0)assert.equal(raw(prime.body[0].ring.marker,0),original[0]);
    const rotation=checkRotation(r,prefix+'upper-swap');
    const capture=compactPath(r.traced.events,prefix+'upper-after-0',{capture:true});
    checkCopy(r,prefix+'upper-after-0',original[i+1],'X1');
    const post=checkExit(r,prefix);paths.push({capture:capture.start,post:post.start});
    assert.ok([guard,original[i+1]].includes(raw(end.ring.P7)));
    assert.deepEqual(nums(end.ring).slice(1),[...original.slice(i+2),...Array(i+1).fill(guard)]);
    const changes=r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&upper.slice(1).includes(w.slot)&&w.nibble%3===1&&w.value!==w.before);
    assert.ok(changes.every(w=>w.command>=rotation.start&&w.command<rotation.end),
      'only the checked four-word ROM rotation moves the unread upper tail');
    const request=stage(r,prefix+'upper-swap').find(e=>e.ip===0xA2&&e.slot==='V');
    assert.equal(raw(end.ring.W),'2F'+request.r[27].toString(16).toUpperCase()+raw(begin.ring.U).slice(3));
    assert.equal(raw(end.ring.Q),raw(begin.ring.V));assert.equal(raw(end.ring.V),guard);
    if(![zero,guard].includes(raw(end.ring.U))) {
      // The first direct copy can format old P7 into U. Its output is
      // already saved; the following zero-U bridge deliberately removes
      // this extra negative-exponent control candidate before re-entry.
      assert.equal(i,0);assert.equal(raw(end.ring.U),original[0]);
      const spillAt=r.traced.events.findIndex(e=>e.stage===prefix+'upper-copy-fifth'&&e.ip===0xE7&&e.slot==='U');
      assert.ok(spillAt>=0);const spill=checkSwapBlock(r,spillAt,1);
      assert.equal(raw(spill.body[0].r,0),original[0]);assert.equal(spill.after.ip,0x47);
      assert.ok(r.traced.writes.filter(w=>w.command>spill.body[0].command&&w.command<end.command&&w.slot==='U'&&w.nibble%3===1)
        .every(w=>w.value===w.before),'the exact copied source, not an unspecified value, remains in U until the next bridge');
    }
  }
  for(const [reg,index] of [[1,0],[6,1],[11,2],[10,3]])
    assert.equal(r.afterRegisters[reg],original[index],'full numeric copy of original upper word '+index);
  const expected=[ '002011100000',original[0],marker,zero,guard,
    '007'+String(paths[2].post==='U'?111:10).padStart(9,'0'),original[1],null,zero,marker,
    original[3],original[2],'001010000000',r.beforeRegisters[13],null ];
  const er=stage(r,'read-2/upper-after-4').find(e=>e.ip===0xD6);
  expected[7]=er.slot==='P10'?'007000000009':'000090000000';
  expected[14]=er.slot==='T'?'007000000002':'000020000000';
  assert.deepEqual(r.afterRegisters,expected,'all 15 ordinary numeric registers match the output/scratch contract');
  for(const [label,index] of [['save-sixth',1],['read-1/zero-source',6],['read-2/zero-source',11]]) {
    const first=at(r,label).command;
    assert.ok(r.traced.writes.filter(w=>w.command>=first&&w.slot===m1[index]&&w.nibble%3===0&&w.nibble<=33)
      .every(w=>w.value===w.before),'saved output survives every later protocol operation: register '+index);
  }
  ordinaryChecks(r);return paths;
}

function checkNegativeZero(r) {
  assert.equal(r.options.skipZeroU,true);
  const fifth=r.before.P7.slice(2),sixth=r.before.P8.slice(2);
  const restart=at(r,'read-1/compact-payload-marker');
  assert.equal(raw(restart.ring.U),fifth);
  assert.equal(raw(restart.ring.V,0),fifth,'first output was correct before the broken re-entry');
  assert.equal(raw(restart.ring.P9,0),sixth,'second output was also correct');
  const spillAt=r.traced.events.findIndex(e=>e.stage==='read-0/upper-copy-fifth'&&e.ip===0xE7&&e.slot==='U');
  assert.ok(spillAt>=0);const spill=checkSwapBlock(r,spillAt,1);
  assert.equal(raw(spill.body[0].r,0),fifth);assert.equal(spill.after.ip,0x47);
  const accepted=stage(r,'read-1/remove-payload-3').find(e=>e.ip===0x9C&&e.slot==='U'&&e.nextIp===0x9E);
  assert.ok(accepted);assert.equal(accepted.raw,fifth,'without the bridge this copied negative exponent becomes a false control');
  assert.equal(r.after.V.slice(2),marker,'hidden V survives the failed exit');
  assert.equal(r.afterRegisters[6],sixth);
  for(const [reg,n] of [[1,'P7'],[11,'P9'],[10,'P10']])assert.notEqual(r.afterRegisters[reg],r.before[n].slice(2));
  assert.deepEqual(r.afterProgram,r.beforeProgram);
  for(const n of ['X','Y','Z','T'])assert.equal(raw(at(r,'done').ring[n]),zero,'zero visible stack is not a successful return');
}

const complex={stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
  fullUpper:['3.2109876E-19','-4.3210987E31','1.2345678E-42','-9.8765432E17']};
const cases=[...[0,1,2].map(phaseOffset=>({...complex,phaseOffset})),
  {...complex,fullUpper:['0','-1E-99','0','-1E-99']},
  {...complex,phaseOffset:1,fullUpper:['1.2345678E99','0','-9.8765432E99','0']},
  {...complex,settleFrames:12,markerFrames:8},
  {stress:true,values:['0','0','0','0'],fullUpper:['0','0','0','0']},
  {...complex,phaseOffset:2,fullUpper:['-1E-99','1E-99','-1E99','1E99'],
    values:['-1E-99','-1.2345678E-42','-9.8765432E99','-7.654321E23']},
  {...complex,initialU:'-1E-99',clearInitialU:true},
  {...complex,phaseOffset:2,initialU:'1.2345678E-42',clearInitialU:true}];

function main() {
  const from=Number(process.env.MS_READ4_FROM??0),limit=Number(process.env.MS_READ4_CASES??cases.length);
  const controlsOnly=process.env.MS_READ4_CONTROLS_ONLY==='1';
  let firstDigest=controlsOnly?process.env.MS_READ4_EXPECTED_DIGEST:undefined;
  const captures=new Set(),posts=new Set();
  if(!controlsOnly)for(const o of cases.slice(from,from+limit)) {
    const r=p.run(o),observedDigest=digest(r.calc);firstDigest??=observedDigest;
    const paths=check(r);paths.forEach(x=>{captures.add(x.capture);posts.add(x.post);});
    console.log('PASS read4:',JSON.stringify(o),JSON.stringify(paths),'all four original upper words in P1/P6/B/A; connected copies/rotations/exit, program and arithmetic = 5.');
    console.log('OBSERVED_DIGEST',observedDigest);
    r.traced.events.length=0;r.traced.writes.length=0;
  }
  if(!controlsOnly) {
    console.log('COVERAGE',JSON.stringify({from,count:Math.min(limit,cases.length-from),captures:[...captures].sort(),posts:[...posts].sort(),firstDigest}));
    if(from||limit<cases.length)return;
    assert.deepEqual([...captures].sort(),['P8','Y']);assert.deepEqual([...posts].sort(),['U','Y']);
  }
  assert.match(firstDigest??'',/^[0-9a-f]{64}$/);
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS observed/unobserved whole core:',firstDigest);
  const repeated=p.runPrepared(plain,{phaseOffset:1});check(repeated);
  console.log('PASS repeat without reset or reseeding: the same protocol reads its current Ms contents.');
  repeated.traced.events.length=0;repeated.traced.writes.length=0;
  const bad=p.run({...complex,pairOnly:true});
  assert.equal(bad.afterRegisters[1],bad.before.P7.slice(2));assert.equal(bad.afterRegisters[6],bad.before.P8.slice(2));
  assert.equal(bad.afterRegisters[10],guard);assert.equal(bad.afterRegisters[11],guard);
  assert.notEqual(bad.afterRegisters[10],bad.before.P10.slice(2));assert.notEqual(bad.afterRegisters[11],bad.before.P9.slice(2));
  for(const n of ['P9','P10'])assert.equal(bad.after[n],bad.before[n]);
  ordinaryChecks(bad);
  console.log('PASS negative control: replacing four-word rotations with pair swaps leaves the last two original words unread, despite two correct copies, clean exit and arithmetic/program = 5.');
  bad.traced.events.length=0;bad.traced.writes.length=0;
  const missed=p.run({...cases[7],skipZeroU:true});checkNegativeZero(missed);
  console.log('PASS negative control: omitting the zero-U bridges accepts the copied fifth word as false control, loses three outputs and leaves hidden V, despite a zero visible stack and unchanged program bytes.');
  console.log('LIMIT: lower Ms is scratch and upper Ms is overwritten. Four upper numeric copies, NOT an eight-word reader/restorer or K1.');
}
if(require.main===module)main();
module.exports={check,checkCopy,checkExit,checkNegativeZero,ordinaryChecks,cases};
