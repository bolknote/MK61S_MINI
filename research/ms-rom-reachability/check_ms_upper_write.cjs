#!/usr/bin/env node
'use strict';
// Native keyboard integration checks, connected to the local symbolic ROM
// contracts. No state injection or synchronizing register/program getters
// between stages; passive trace snapshots do not drive execution.
const assert=require('node:assert/strict');
const one=require('./probe_ms_upper_write1.cjs');
const pair=require('./probe_ms_upper_write2.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {compactPath}=require('./check_ms_read6_exit.cjs');
const {checkPairedPath}=require('./check_ms_upper_read2_exit.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const names=['P7','P8','P9','P10'],msNames=['U','V','W','Q',...names];
const zero='000000000000',marker='0000F0000000',guard='958912345678';
const stage=(r,label)=>r.traced.events.filter(e=>e.stage===label);
const ringAt=(r,label)=>stage(r,label).find(e=>e.ring).ring;
const numeric=ring=>names.map(n=>raw(ring[n]));

function checkRotation(r,label) {
  const rows=stage(r,label),request=rows.find(e=>e.ip===0xA2&&e.slot==='V');
  assert.ok(request);assert.deepEqual([request.r[32],request.r[35]],[5,2]);
  const at=rows.findIndex(e=>e.otherChips?.[4].ip===0x3A);assert.ok(at>=0);
  const block=rows.slice(at,at+5),original=block[0].ring,values=numeric(original);
  assert.equal(values[0],guard,'the stale formatter source was guarded');
  const bufferAt=rows.findLastIndex((e,i)=>i<at&&e.otherChips?.[4].ip===0xD4&&e.otherChips[4].slot==='Q');
  assert.ok(bufferAt>=0);const buffer=rows[bufferAt].otherChips[4];
  assert.deepEqual([buffer.l,buffer.s1,...[37,38,40,41].map(i=>buffer.r[i])],[1,9,4,0,13,6]);
  assert.equal(raw(buffer.r,2),values[0]);assert.equal(raw(buffer.r,1),values[1]);
  assert.deepEqual([0,1,2].map(i=>buffer.st[36+i]+16*buffer.st[39+i]),[0x29,0x3A,0x3A]);
  assert.deepEqual(rows.slice(bufferAt,at+1).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [...['Q',...names].map(n=>[0xD4,n]),[0xC4,'marker'],[0x2C,'control'],[0x3B,'X1'],
      [0x2B,'X'],[0x60,'Y'],...['Z','T','U','V'].map(n=>[0x37,n]),[0x27,'W'],[0x61,'Q'],[0x3A,'P7']]);
  const c=block[0].otherChips[4];assert.equal(c.s1,5);assert.equal(raw(c.r,0),values[0]);
  assert.deepEqual([0,1,2].map(l=>raw(c.st,l)),values.slice(1));
  assert.deepEqual(block.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [[0x3A,'P7'],[0x3A,'P8'],[0x3A,'P9'],[0x2A,'P10'],[0x39,'marker']]);
  const expected=structuredClone(original);
  for(let i=0;i<4;i++)for(let j=0;j<12;j++)expected[names[i]][1+3*j]=original[names[(i+1)%4]][1+3*j];
  assert.deepEqual(block[4].ring,expected,'rotation changes exactly the upper four numerical words among all 630 tetras');
  const writes=r.traced.writes.filter(w=>w.command>=block[0].command&&w.command<block[4].command);
  assert.equal(writes.length,48);assert.ok(writes.every(w=>w.chip===4&&w.nibble%3===1&&w.nibble<=34&&
    ((w.ip===0x3A&&names.slice(0,3).includes(w.slot))||(w.ip===0x2A&&w.slot==='P10'))));
  const early=r.traced.writes.filter(w=>w.command>=rows[bufferAt].command&&w.command<block[0].command);
  assert.ok(early.filter(w=>names.includes(w.slot)&&w.nibble%3===1).every(w=>w.value===w.before));
  // Same guarded 40..E7 suffix as the separate IK1302 theorem, now after
  // the longer IK1303 four-word rotation, not an assumed two-word timing.
  const f=rows.findIndex(e=>e.ip===0x40);assert.ok(f>=0);
  assert.deepEqual([rows[f].slot,rows[f].s1,raw(rows[f].r,0)],['Z',9,guard]);
  const seq=[0x40,0x41,0x42,0x46];
  const slot=()=>slots[(slots.indexOf('Z')+seq.length)%15];
  while(!['marker','V'].includes(slot()))seq.push(0xE5);
  seq.push(0xE5,0xE6,0xE8,0xE7);
  assert.deepEqual(rows.slice(f,f+seq.length).map(e=>[e.ip,e.slot]),
    seq.map((ip,i)=>[ip,slots[(slots.indexOf('Z')+i)%15]]));
  const end=checkSwapBlock(r,r.traced.events.indexOf(rows[f+seq.length-1]),1);
  assert.equal(end.body[0].slot,'X');assert.equal(raw(end.body[0].r,0),guard);assert.equal(end.after.ip,0x47);
  assert.deepEqual(numeric(end.after.ring),[...values.slice(1),guard]);
  return {start:block[0].command,end:block[4].command};
}

function checkUpperPush(r,label,source,{sourceIndex=10}={}) {
  assert.ok(Number.isInteger(sourceIndex)&&sourceIndex>=8&&sourceIndex<=14);
  const rows=stage(r,label),at=rows.findIndex(e=>e.ip===0xD6),first=rows[at];assert.ok(first);
  const word=raw(first.m,0),entries={Z:'007'+String(sourceIndex).padStart(9,'0'),P9:'0000'+(sourceIndex-8)+'0000000'};
  assert.equal(word,entries[first.slot]);
  assert.deepEqual([first.r[29],first.r[32],first.r[35],first.r[26],first.s1],[14,13,0,15,6]);
  assert.deepEqual(first.sp,[0x2F,0xAC,0x9A]);
  const pointer=first.slot==='Z'?sourceIndex:sourceIndex-8;
  const seq=[0xD6,...Array.from({length:7-Number(word.slice(0,3))},()=>[0x2F,0x20]).flat(),0x2F,0x21,0x23,0x25];
  const slot=()=>slots[(slots.indexOf(first.slot)+seq.length)%15];
  const helper=(n,load=false)=>{
    while(!['marker','V'].includes(slot()))seq.push(1);
    seq.push(1,...Array(n+1).fill(2),3,4,0xBA,0xCB,0xDD,load?0xD6:0xD4);
  };
  helper(13);seq.push(0x26,0x28,0x7E,0x70,0xAB,0xAD,0xA6);helper(pointer,true);
  seq.push(0xA7);while(!['marker','V'].includes(slot()))seq.push(0xE5);
  seq.push(0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9);
  const path=rows.slice(at,at+seq.length);
  assert.deepEqual(path.map(e=>[e.ip,e.slot]),seq.map((ip,i)=>[ip,slots[(slots.indexOf(first.slot)+i)%15]]),
    'the complete native pointer/read/write path matches the symbolic contract');
  for(const e of path)if([1,0xE5].includes(e.ip))assert.equal(e.m[22]===15,['marker','V'].includes(e.slot));
  const d4=path.filter(e=>e.ip===0xD4);assert.deepEqual(d4.map(e=>e.slot),[first.slot]);
  const writes=r.traced.writes.filter(w=>w.command===d4[0].command);
  assert.equal(writes.length,12);assert.ok(writes.every(w=>w.chip===3&&w.nibble%3===0&&w.nibble<=33));
  assert.equal(writes.map(w=>w.value.toString(16).toUpperCase()).reverse().join(''),'007'+String(pointer).padStart(9,'0'));
  const read=path.filter(e=>e.ip===0xD6)[1];assert.equal(read.slot,slots[(sourceIndex+7)%15]);assert.equal(raw(read.m,0),source);
  const block=checkSwapBlock(r,r.traced.events.indexOf(path.find(e=>e.ip===0xE7)),4);
  assert.deepEqual(block.body.map(e=>e.slot),names);assert.equal(raw(block.body[0].r,0),source);
  assert.equal(block.after.ip,0xA9);assert.equal(block.after.nextIp,0xAC);
  const returned=rows[rows.indexOf(block.after)+1];assert.equal(returned.ip,0xAC);assert.equal(returned.s1,0);
  for(let i=0;i<10;i++)assert.equal(returned.r[3*i],block.after.r[3*i]);
  assert.equal(returned.r[30],block.after.r[32]);assert.equal(returned.r[33],block.after.r[35]);
  return {entry:first.slot,start:block.body[0].command,end:block.after.command};
}

function checkExit(r,prefix) {
  const es=r.traced.events;
  for(let i=1;i<=3;i++) {
    const label=prefix+'upper-after-'+i;compactPath(es,label);
    const block=checkSwapBlock(r,es.findIndex(e=>e.stage===label&&e.ip===0xE7&&e.nextIp===0xA8),4);
    assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);assert.equal(raw(block.body[0].r,0),zero);
    assert.ok(stage(r,label).filter(e=>e.ip===0xE7).every(e=>e.slot==='X'));
  }
  checkPairedPath(es,prefix+'upper-after-4',14,'W');
  const marked=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'upper-after-4'&&e.ip===0xE7&&e.nextIp===0xA8),4);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(marked.after.ring[n])),[marker,zero,zero,zero]);
  const post=compactPath(es,prefix+'upper-after-5',{postMarker:true,postPointer:110});
  const shifted=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'upper-after-5'&&e.ip===0xE7&&e.nextIp===0xA8),4);
  assert.equal(raw(shifted.body[0].r,0),zero);assert.equal(raw(shifted.after.ring.Y),marker);assert.equal(raw(shifted.after.ring.Z),zero);
  const erased=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'upper-after-6'&&e.ip===0xE7&&e.slot==='V'),1);
  assert.equal(erased.body[0].raw,marker);assert.equal(raw(erased.body[0].r,0),guard);assert.equal(erased.after.ip,0x47);
  return post.start;
}

function checkOne(r,prefix,before,after,source) {
  const es=r.traced.events,prime=es.findIndex(e=>e.stage===prefix+'upper-prime'&&e.ip===0xE7&&e.slot==='P7');
  assert.ok(prime>=0);const guarded=checkSwapBlock(r,prime,1);
  assert.equal(raw(guarded.body[0].r,0),guard);assert.deepEqual(numeric(guarded.body[0].ring),numeric(before));
  assert.equal(raw(guarded.body[0].ring.marker,0),zero,'unused old-top backup was removed');
  assert.equal(stage(r,prefix+'upper-copy-fifth').length,0);
  assert.deepEqual(numeric(guarded.after.ring),[guard,...numeric(before).slice(1)]);
  const rotation=checkRotation(r,prefix+'upper-swap');
  const push=checkUpperPush(r,prefix+'upper-after-0',source),post=checkExit(r,prefix);
  assert.deepEqual(numeric(after),[source,...numeric(before).slice(1)]);
  assert.equal(raw(after.U),zero);assert.equal(raw(after.V),guard);
  const request=stage(r,prefix+'upper-swap').find(e=>e.ip===0xA2&&e.slot==='V');
  assert.equal(raw(after.W),'2F'+request.r[27].toString(16).toUpperCase()+raw(before.U).slice(3));
  assert.equal(raw(after.Q),raw(before.V));
  const pointerRead=stage(r,prefix+'upper-after-4').find(e=>e.ip===0xD6);
  const expectedRegisters=[
    '002011000000',raw(before.V,0),marker,zero,guard,
    '007'+String(post==='U'?110:10).padStart(9,'0'),
    push.entry==='P9'?'007000000002':'000020000000',
    pointerRead.slot==='P10'?'007000000009':'000090000000',
    zero,marker,source,raw(before.X,0),'001010000000','007000000010',
    pointerRead.slot==='T'?'007000000002':'000020000000'];
  assert.deepEqual(msNames.concat(['marker','control','X1','X','Y','Z','T']).map(n=>raw(after[n],0)),expectedRegisters,
    'all ordinary words have exactly the declared source or scratch contents');
  for(const n of ['X','Y','Z','T'])assert.equal(raw(after[n]),zero);
  const from=stage(r,prefix+'prepare-zero-p8')[0].command;
  const until=stage(r,prefix+'upper-after-9').at(-1).command+1;
  const moved=r.traced.writes.filter(w=>w.command>=from&&w.command<until&&names.slice(1).includes(w.slot)&&w.nibble%3===1&&w.value!==w.before);
  assert.ok(moved.every(w=>(w.command>=rotation.start&&w.command<rotation.end)||(w.command>=push.start&&w.command<push.end)),
    'last three upper words change only during the checked rotation and push; their final contents are restored');
  return {push:push.entry,post};
}

function checkMiddle(r,source) {
  const prefix='sixth-to-second/',es=r.traced.events,rows=stage(r,prefix+'upper-swap');
  const at=rows.findIndex(e=>e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='P7');assert.ok(at>=0);
  const block=rows.slice(at,at+3),first=block[0],c=first.otherChips[4];
  assert.deepEqual(block.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x4E,'P7'],[0x2A,'P8'],[0x39,'P9']]);
  assert.equal(raw(first.ring.P7),source);assert.equal(raw(c.r,0),raw(first.ring.P8));
  const expected=structuredClone(first.ring);
  for(let i=0;i<12;i++){expected.P7[1+3*i]=first.ring.P8[1+3*i];expected.P8[1+3*i]=first.ring.P7[1+3*i];}
  assert.deepEqual(block[2].ring,expected);
  const writes=r.traced.writes.filter(w=>w.command>=first.command&&w.command<block[2].command);
  assert.equal(writes.length,24);assert.ok(writes.every(w=>w.chip===4&&['P7','P8'].includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
  compactPath(es,prefix+'upper-after-0',{capture:true});
  const post=checkExit(r,prefix),done=ringAt(r,'copy-fifth-source');
  assert.equal(raw(done.P8),source);
  for(const n of ['P9','P10'])assert.equal(raw(done[n]),raw(first.ring[n]));
  for(const n of ['X','Y','Z','T'])assert.equal(raw(done[n]),zero);
  assert.equal(stage(r,prefix+'upper-copy-fifth').length,0);
  assert.equal(raw(done.U),zero);assert.equal(raw(done.V),guard);
  return post;
}

function checkCommon(r) {
  assert.deepEqual(r.afterProgram,r.beforeProgram);assert.deepEqual(r.traced.primitives,[]);
  assert.ok(r.traced.events.every(e=>e.ip!==0xC9));
  const changed=r.traced.writes.filter(w=>msNames.includes(w.slot)&&w.nibble%3===1&&w.value!==w.before);
  assert.ok(changed.every(w=>w.nibble<=34),'all eight Ms service fields remain unchanged throughout');
  for(const n of msNames)assert.equal(r.after[n].slice(0,2),r.before[n].slice(0,2));
  const done=ringAt(r,'done');
  for(const n of ['X','Y','Z','T'])assert.equal(raw(done[n]),zero);
  for(const n of msNames)assert.notEqual(done[n][22],15,'no false Ms marker remains');
  for(const i of [1,11])assert.equal(r.afterRegisters[i],r.beforeRegisters[i],'retained source/register '+i);
  r.calc.inputNumber('2',{clear:true}).press('В↑').inputNumber('3').press('+').runFrames(8);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),r.afterRegisters);assert.deepEqual(program(r.calc),r.beforeProgram);
  r.calc.pressSequence(['В/О','С/П']).runFrames(12);aligned(r.calc);
  assert.equal(r.calc.displayText(),'5,');assert.equal(r.calc.programCounter(),'05');
  assert.deepEqual(fullMsPages(r.calc),r.after);assert.deepEqual(registers(r.calc),r.afterRegisters);assert.deepEqual(program(r.calc),r.beforeProgram);
}

function checkPair(r) {
  const sixth=r.beforeRegisters[10],fifth=r.beforeRegisters[11];
  const a=checkOne(r,'sixth-to-top/',ringAt(r,'sixth-to-top/prepare-zero-p8'),
    ringAt(r,'sixth-to-second/compact-payload-marker'),sixth);
  const middle=checkMiddle(r,sixth);
  const b=checkOne(r,'fifth-to-top/',ringAt(r,'fifth-to-top/prepare-zero-p8'),ringAt(r,'done'),fifth);
  assert.deepEqual(names.map(n=>r.after[n]),[r.before.P7.slice(0,2)+fifth,r.before.P8.slice(0,2)+sixth,r.before.P9,r.before.P10]);
  assert.equal(r.afterRegisters[10],fifth);
  assert.equal(r.afterRegisters[9],marker);assert.equal(r.after.U.slice(2),zero);
  checkCommon(r);return {pushes:[a.push,b.push],posts:[a.post,middle,b.post]};
}

function main() {
  const complex={stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
    fullUpper:['3.2109876E-19','-4.3210987E31','1.2345678E-42','-9.8765432E17']};
  const cases=[...[0,1,2].map(phaseOffset=>({...complex,phaseOffset})),
    {...complex,fifth:'0',sixth:'-1E-99'},
    {...complex,phaseOffset:1,fifth:'1.2345678E99',sixth:'0'},
    {...complex,phaseOffset:2,fifth:'-1E-99',sixth:'-9.8765432E99'},
    {...complex,settleFrames:12,markerFrames:8},
    {stress:true,fifth:'0',sixth:'0',upperValues:['0','0','333','444']}];
  let firstDigest;const pushes=new Set(),posts=new Set();
  const from=Number(process.env.MS_WRITE_FROM??0),limit=Number(process.env.MS_WRITE_CASES??cases.length);
  for(const o of cases.slice(from,from+limit)) {
    const r=pair.run(o);firstDigest??=digest(r.calc);const paths=checkPair(r);
    paths.pushes.forEach(x=>pushes.add(x));paths.posts.forEach(x=>posts.add(x));
    console.log('PASS:',JSON.stringify(o),'B -> Ms P7; A -> Ms P8; last two preserved; connected ROM blocks, all ring tetras, clean exit, arithmetic and program = 5.');
  }
  if(from||limit<cases.length)return;
  assert.deepEqual([...pushes].sort(),['P9','Z']);assert.deepEqual([...posts].sort(),['U','Y']);
  const plain=pair.prepare(cases[0]);pair.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS: observed/unobserved complete core state:',firstDigest);
  const single=one.run({...complex,source:'-8.7654321E-17'});
  checkOne(single,'',ringAt(single,'prepare-zero-p8'),ringAt(single,'done'),single.beforeRegisters[10]);
  assert.deepEqual(names.map(n=>single.after[n]),[single.before.P7.slice(0,2)+single.beforeRegisters[10],...names.slice(1).map(n=>single.before[n])]);
  checkCommon(single);console.log('PASS: standalone one-word writer preserves the other three nonzero upper Ms words.');
  const missed=pair.run({...cases[3],legacyCopy:true}),dirty=ringAt(missed,'copy-fifth-source');
  assert.equal(raw(dirty.U),missed.beforeRegisters[10]);
  for(const n of ['P9','P10'])assert.equal(raw(dirty[n],1,14),missed.before[n]);
  assert.ok(missed.traced.events.some(e=>e.stage.startsWith('fifth-to-top/')&&e.ip===0x9C&&e.slot==='U'&&e.nextIp===0x9E),
    'negative-exponent U is accepted as control on re-entry');
  assert.notDeepEqual(names.slice(2).map(n=>missed.after[n]),names.slice(2).map(n=>missed.before[n]));
  const spillAt=missed.traced.events.findIndex(e=>e.stage==='sixth-to-second/upper-copy-fifth'&&e.ip===0xE7&&e.slot==='U');
  assert.ok(spillAt>=0);const spill=checkSwapBlock(missed,spillAt,1);
  assert.equal(raw(spill.body[0].r,0),missed.beforeRegisters[10]);assert.equal(spill.after.ip,0x47);
  console.log('PASS: negative control with the unnecessary old-top copy: sixth=-1E-99 is formatted into U, false control is accepted, and the last two Ms words are corrupted despite a zero visible stack.');
  const upper=require('./probe_ms_upper_swap.cjs');
  const options={stress:true,sourceKeys:['F',','],beforeSwapKeys:['П→X','2'],afterKeys:[['F',',']]};
  const calc=upper.prepare(options);inputLiteral(calc,'-1.2345678E-42');calc.pressSequence(['X→П','2']);aligned(calc);
  const negative=upper.runPrepared(calc,options);
  assert.ok(stage(negative,'upper-swap').some(e=>e.ip===0xA3&&e.slot==='W'));
  assert.ok(stage(negative,'upper-after-0').some(e=>e.ip===0xA3&&e.slot==='control'));
  assert.notDeepEqual(names.map(n=>negative.after[n].slice(2)),[negative.before.P9,negative.before.P10,negative.before.P7,negative.before.P8].map(x=>x.slice(2)));
  console.log('PASS: negative control: immediate second F comma returns through real control, not a second upper rotation.');
  console.log('LIMIT: lower Ms and ordinary scratch are modified; initial lower U must pass the existing marker-entry domain. Not yet integrated with the six-word reader; last two words not read; NOT K1/K2.');
}
if(require.main===module)main();
module.exports={checkUpperPush,checkRotation,checkOne,checkPair,checkCommon};
