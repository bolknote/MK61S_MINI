#!/usr/bin/env node
'use strict';
// Native integration of the four local zero-loader contracts. Checks complete
// ROM paths, all 630 ring tetras in transfers, retained P3, and finite use after
// exit. No synchronizing getters or trace-dependent actions inside a protocol.
const assert=require('node:assert/strict');
const one=require('./probe_ms_zero_p0.cjs');
const pair=require('./probe_ms_zero_pair.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {checkRotation,checkUpperPush,checkCommon}=require('./check_ms_upper_write.cjs');
const {checkPairedPath}=require('./check_ms_upper_read2_exit.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const slots=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
const upper=['P7','P8','P9','P10'];
const registerSlots=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
const zero='000000000000',marker='0000F0000000',guard='958912345678';
const rows=(r,label)=>r.traced.events.filter(e=>e.stage===label);
const ringAt=(r,label)=>rows(r,label).find(e=>e.ring).ring;
const numeric=ring=>upper.map(n=>raw(ring[n]));

function zeroPath(r,label,postMarker=false) {
  const es=rows(r,label),at=es.findIndex(e=>e.ip===0xD6),first=es[at];assert.ok(first);
  const entries=postMarker?{Y:'000070000000',U:zero}:{Y:'000070000000',P8:'007000000007'};
  const word=raw(first.m,0);assert.equal(word,entries[first.slot]);
  assert.deepEqual([first.r[29],first.r[32],first.r[35],first.r[26],first.s1],[13,12,0,15,6]);
  assert.deepEqual(first.sp,[0x2F,0xAC,0x9A]);
  const pointer=word===zero?0:7,markers=new Set(['marker','V',...(postMarker?['X']:[])]);
  const seq=[0xD6,...Array.from({length:7-Number(word.slice(0,3))},()=>[0x2F,0x20]).flat(),0x2F,0x21,0x23,0x25];
  const slot=()=>slots[(slots.indexOf(first.slot)+seq.length)%15];
  const helper=(n,load=false)=>{
    while(!markers.has(slot()))seq.push(1);
    seq.push(1,...Array(n+1).fill(2),3,4,0xBA,0xCB,0xDD,load?0xD6:0xD4);
  };
  helper(12);seq.push(0x26,0x28,0x7E,0x70,0xAB,0xAD,0xA6);helper(pointer,true);
  seq.push(0xA7);while(!markers.has(slot()))seq.push(0xE5);
  seq.push(0xE5,0xE6,0xE8,0xE7,0xA8,0xA8,0xA8,0xA9);
  const path=es.slice(at,at+seq.length);
  assert.deepEqual(path.map(e=>[e.ip,e.slot]),seq.map((ip,i)=>[ip,slots[(slots.indexOf(first.slot)+i)%15]]),
    'each native command and physical slot matches the corresponding symbolic contract');
  for(const e of path)if([1,0xE5].includes(e.ip))assert.equal(e.m[22]===15,markers.has(e.slot));
  const d4=path.filter(e=>e.ip===0xD4);assert.deepEqual(d4.map(e=>e.slot),[pointer===0?'Y':'P8']);
  const writes=r.traced.writes.filter(w=>w.command===d4[0].command);
  assert.equal(writes.length,12);assert.ok(writes.every(w=>w.chip===3&&w.nibble%3===0&&w.nibble<=33));
  assert.equal(writes.map(w=>w.value.toString(16).toUpperCase()).reverse().join(''),'007'+String(pointer).padStart(9,'0'));
  const read=path.filter(e=>e.ip===0xD6)[1];assert.equal(read.slot,'U');assert.equal(raw(read.m,0),zero);
  const block=checkSwapBlock(r,r.traced.events.indexOf(path.find(e=>e.ip===0xE7)),4);
  assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);assert.equal(raw(block.body[0].r,0),zero);
  assert.equal(block.after.nextIp,0xAC);
  assert.ok(es.filter(e=>e.ip===0xE7).every(e=>e.slot==='X'),'zero formatter never spills into Ms');
  return {entry:first.slot,block};
}

function checkExit(r,prefix) {
  const zeros=[];
  for(let i=1;i<=3;i++)zeros.push(zeroPath(r,prefix+'upper-after-'+i).entry);
  checkPairedPath(r.traced.events,prefix+'upper-after-4',14,'W');
  const marked=checkSwapBlock(r,r.traced.events.findIndex(e=>e.stage===prefix+'upper-after-4'&&e.ip===0xE7&&e.nextIp===0xA8),4);
  assert.deepEqual(['X','Y','Z','T'].map(n=>raw(marked.after.ring[n])),[marker,zero,zero,zero]);
  const post=zeroPath(r,prefix+'upper-after-5',true);
  assert.equal(raw(post.block.after.ring.Y),marker);assert.equal(raw(post.block.after.ring.Z),zero);
  const erased=checkSwapBlock(r,r.traced.events.findIndex(e=>e.stage===prefix+'upper-after-6'&&e.ip===0xE7&&e.slot==='V'),1);
  assert.equal(erased.body[0].raw,marker);assert.equal(raw(erased.body[0].r,0),guard);assert.equal(erased.after.ip,0x47);
  for(let i=7;i<=8;i++) {
    const read=rows(r,prefix+'upper-after-'+i).find(e=>e.ip===0xD6);
    assert.equal(read.slot,'U');assert.equal(raw(read.m,0),zero,'final direct recalls also use P0, not retained P3');
  }
  return {zeros,post:post.entry};
}

function checkRegisters(r,prefix,before,after,source,push,post,{keepP8=false,sourceIndex=10}={}) {
  const ptr=rows(r,prefix+'upper-after-4').find(e=>e.ip===0xD6);
  const expected=[zero,raw(before.V,0),marker,raw(before.Q,0),guard,'007000000007',
    push==='P9'?'007'+String(sourceIndex-8).padStart(9,'0'):'0000'+(sourceIndex-8)+'0000000',
    ptr.slot==='P10'?'007000000009':'000090000000',
    keepP8?raw(before.marker,0):zero,marker,sourceIndex===10?source:raw(before.X1,0),raw(before.X,0),post==='U'?'007000000000':'000070000000',
    '007'+String(sourceIndex).padStart(9,'0'),ptr.slot==='T'?'007000000002':'000020000000'];
  assert.deepEqual(registerSlots.map(n=>raw(after[n],0)),expected,'all 15 ordinary registers have exactly declared payload or scratch values');
  for(const n of ['X','Y','Z','T'])assert.equal(raw(after[n]),zero);
}

function checkOne(r,prefix,before,after,source,variant={}) {
  const es=r.traced.events;
  if(variant.keepP8) {
    const load=rows(r,prefix+'shift-0').find(e=>e.ip===0xD6);
    assert.equal(load.slot,'marker');assert.equal(raw(load.m,0),raw(before.marker,0));
    const shifted=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'shift-0'&&e.ip===0xE7&&e.slot==='U'),4);
    assert.deepEqual(shifted.body.map(e=>e.slot),['U','V','W','Q']);
    assert.equal(raw(shifted.body[0].r,0),raw(before.marker,0));
    assert.equal(raw(shifted.after.ring.U),raw(before.marker,0));
    assert.equal(raw(shifted.after.ring.V),marker,'retained P8 replaces the old zero seed without losing the V marker');
  }
  const prime=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'upper-prime'&&e.ip===0xE7&&e.slot==='P7'),1);
  assert.equal(raw(prime.body[0].r,0),guard);assert.deepEqual(numeric(prime.body[0].ring),numeric(before));
  assert.equal(raw(prime.body[0].ring.marker,0),variant.keepP8?raw(before.marker,0):zero);
  assert.equal(rows(r,prefix+'upper-copy-fifth').length,0);
  assert.deepEqual(numeric(prime.after.ring),[guard,...numeric(before).slice(1)]);
  const rotation=checkRotation(r,prefix+'upper-swap'),push=checkUpperPush(r,prefix+'upper-after-0',source,variant);
  const exit=checkExit(r,prefix);
  assert.deepEqual(numeric(after),[source,...numeric(before).slice(1)]);
  assert.equal(raw(after.U),variant.keepP8?raw(before.marker,0):zero);assert.equal(raw(after.V),guard);assert.equal(raw(after.Q),raw(before.V));
  const request=rows(r,prefix+'upper-swap').find(e=>e.ip===0xA2&&e.slot==='V');
  assert.equal(raw(after.W),'2F'+request.r[27].toString(16).toUpperCase()+raw(before.U).slice(3));
  checkRegisters(r,prefix,before,after,source,push.entry,exit.post,variant);
  const from=rows(r,prefix+'prepare-zero-p8')[0].command,until=rows(r,prefix+'upper-after-9').at(-1).command+1;
  const moved=r.traced.writes.filter(w=>w.command>=from&&w.command<until&&upper.slice(1).includes(w.slot)&&w.nibble%3===1&&w.before!==w.value);
  assert.ok(moved.every(w=>(w.command>=rotation.start&&w.command<rotation.end)||(w.command>=push.start&&w.command<push.end)),
    'last three upper words change only in the checked rotation and push and are finally restored');
  return {...exit,push:push.entry};
}

function checkMiddle(r,source,{prefix='sixth-to-second/',doneLabel='copy-fifth-source',...variant}={}) {
  const es=rows(r,prefix+'upper-swap');
  const at=es.findIndex(e=>e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='P7');assert.ok(at>=0);
  const block=es.slice(at,at+3),first=block[0],before=first.ring;
  assert.deepEqual(block.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x4E,'P7'],[0x2A,'P8'],[0x39,'P9']]);
  assert.equal(raw(before.P7),source);assert.equal(raw(first.otherChips[4].r,0),raw(before.P8));
  const expected=structuredClone(before);
  for(let i=0;i<12;i++){expected.P7[1+3*i]=before.P8[1+3*i];expected.P8[1+3*i]=before.P7[1+3*i];}
  assert.deepEqual(block[2].ring,expected,'middle exchange changes exactly 24 of all 630 tetras');
  const writes=r.traced.writes.filter(w=>w.command>=first.command&&w.command<block[2].command);
  assert.equal(writes.length,24);assert.ok(writes.every(w=>w.chip===4&&['P7','P8'].includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
  assert.equal(rows(r,prefix+'upper-after-0').length,0,'no unused BC capture in the middle');
  const exit=checkExit(r,prefix),done=ringAt(r,doneLabel);
  assert.equal(raw(done.P8),source);
  for(const n of ['P9','P10'])assert.equal(raw(done[n]),raw(before[n]));
  assert.equal(raw(done.U),variant.keepP8?raw(before.marker,0):zero);assert.equal(raw(done.V),guard);
  checkRegisters(r,prefix,before,done,source,'none',exit.post,variant);
  return exit;
}

function retained(r) {
  for(const i of [1,3,11])assert.equal(r.afterRegisters[i],r.beforeRegisters[i],'retained ordinary P'+i);
  const changes=r.traced.writes.filter(w=>['V','Q','X'].includes(w.slot)&&w.nibble%3===0&&w.nibble<=33&&w.value!==w.before);
  assert.deepEqual(changes,[],'P1, P3 and B numerical words are not changed even temporarily');
  assert.notEqual(r.beforeRegisters[3],guard,'payload is not the guard constant');
  checkCommon(r);
}

function checkPair(r) {
  const sixth=r.beforeRegisters[10],fifth=r.beforeRegisters[11];
  const a=checkOne(r,'sixth-to-top/',ringAt(r,'sixth-to-top/prepare-zero-p8'),ringAt(r,'sixth-to-second/zero-p0'),sixth);
  const middle=checkMiddle(r,sixth);
  const b=checkOne(r,'fifth-to-top/',ringAt(r,'fifth-to-top/prepare-zero-p8'),ringAt(r,'done'),fifth);
  assert.deepEqual(upper.map(n=>r.after[n]),[r.before.P7.slice(0,2)+fifth,r.before.P8.slice(0,2)+sixth,r.before.P9,r.before.P10]);
  retained(r);return [a,middle,b];
}

function main() {
  const complex={stress:true,values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
    fullUpper:['3.2109876E-19','-4.3210987E31','1.2345678E-42','-9.8765432E17']};
  const cases=[...[0,1,2].map(phaseOffset=>({...complex,phaseOffset})),
    {...complex,payload:'-1E-99',fifth:'0',sixth:'-1E-99'},
    {...complex,phaseOffset:1,payload:'1.2345678E99',fifth:'1.2345678E99',sixth:'0'},
    {...complex,phaseOffset:2,payload:'0',fifth:'-1E-99',sixth:'-9.8765432E99'},
    {...complex,settleFrames:12,markerFrames:8},
    {stress:true,payload:'12345678',fifth:'0',sixth:'0',upperValues:['0','0','333','444']}];
  const from=Number(process.env.MS_ZERO_FROM??0),limit=Number(process.env.MS_ZERO_CASES??cases.length);
  let firstDigest;const pushes=new Set(),posts=new Set(),zeros=new Set();
  for(const o of cases.slice(from,from+limit)) {
    const r=pair.run(o);firstDigest??=digest(r.calc);
    for(const path of checkPair(r)){if(path.push)pushes.add(path.push);posts.add(path.post);path.zeros.forEach(x=>zeros.add(x));}
    console.log('PASS pair:',JSON.stringify(o),'upper pair written, last two preserved, P1/P3/B retained throughout; exact transfers and 15-register result; arithmetic/program = 5.');
  }
  if(from||limit<cases.length)return;
  assert.deepEqual([...pushes].sort(),['P9','Z']);assert.deepEqual([...posts].sort(),['U','Y']);assert.deepEqual([...zeros].sort(),['P8','Y']);
  const plain=pair.prepare(cases[0]);pair.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS observed/unobserved complete state:',firstDigest);
  for(const phaseOffset of [0,1,2]) {
    const r=one.run({...complex,phaseOffset});
    checkOne(r,'',ringAt(r,'prepare-zero-p8'),ringAt(r,'done'),r.beforeRegisters[10]);retained(r);
    console.log('PASS standalone phase',phaseOffset,'source A, three other upper words and P1/P3/B preserved.');
  }
  console.log('LIMIT: one extra retained register, not a lossless six-word reader/writer composition or K1/K2. Lower Ms and declared ordinary scratch remain modified.');
}
if(require.main===module)main();
module.exports={zeroPath,checkExit,checkOne,checkMiddle,checkPair,retained};
