#!/usr/bin/env node
'use strict';
// Native four-pair exchange. All final comparisons use both ORIGINAL banks.
const assert=require('node:assert/strict');
const p=require('./probe_ms_lower_exchange.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {checkQRead,checkSecondaryWRead}=require('./check_ms_upper_roundtrip.cjs');
const {checkLowerPush}=require('./check_ms_read6_roundtrip.cjs');
const {ordinaryChecks}=require('./check_ms_upper_read4.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const lower=['U','V','W','Q'],upper=['P7','P8','P9','P10'];
const m1=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
const zero='000000000000';
const rows=(r,label)=>r.traced.events.filter(e=>e.stage===label);
const at=(r,label)=>rows(r,label).find(e=>e.ring);
const numeric=ms=>lower.map(n=>ms[n].slice(2));

function checkStore(r,label,word,sourceSlot='X',destination='control') {
  const es=r.traced.events,ds=es.filter(e=>e.stage===label&&e.ip===0xD4);assert.equal(ds.length,1);
  // The stage can contain the normal return's later EE(X) as well. Only
  // the EE preceding this D4 is the source of the actual register store.
  const reads=rows(r,label).filter(e=>e.ip===0xEE&&e.command<ds[0].command);
  assert.equal(reads.length,1);const source=reads[0];
  assert.equal(source.slot,sourceSlot);assert.equal(source.raw,word);
  const index=es.indexOf(ds[0]),write=ds[0],next=es[index+1];
  assert.equal(write.slot,destination);assert.equal(next.ip,0xA5);
  const expected=structuredClone(write.ring);
  for(let j=0;j<12;j++)expected[destination][3*j]=source.m[1+3*j];
  assert.deepEqual(next.ring,expected,'D4 changes exactly 12 M1 tetras among all 630');
  const writes=r.traced.writes.filter(w=>w.command===write.command);
  assert.equal(writes.length,12);
  assert.ok(writes.every(w=>w.chip===3&&w.slot===destination&&w.nibble%3===0&&w.nibble<=33));
}

function checkU(r) {
  const es=r.traced.events,word=r.before.U.slice(2),prefix='read-u/';
  const request=rows(r,prefix+'swap-read-u').find(e=>e.ip===0xA2);
  assert.ok(request);assert.equal(request.slot,'X');assert.equal(request.m[22],15);
  assert.deepEqual([32,35,27,37,40].map(i=>request.r[i]),[4,1,0,3,13]);
  const wi=es.findIndex(e=>e.stage===prefix+'swap-read-u'&&e.otherChips?.[4].ip===0x4E);
  assert.ok(wi>=0);const writer=es[wi].otherChips[4];
  assert.equal(writer.slot,'X');assert.equal(writer.m[22],15);assert.equal(raw(writer.r,0),word);
  const si=es.findLastIndex((e,i)=>i<wi&&e.otherChips?.[4].ip===0x53);assert.ok(si>=4);
  const source=es[si].otherChips[4],path=es.slice(si-4,si).map(e=>e.otherChips[4]);
  assert.deepEqual(path.map(e=>[e.ip,e.slot]),[[0x6E,'X'],[0x5E,'Y'],[0x50,'Z'],[0x52,'T']]);
  assert.equal(path[0].r[29],0);assert.equal(path[0].m[22],15);
  assert.deepEqual([34,31,28].map(i=>path[1].m[i]),[1,4,0]);
  assert.equal(raw(path[2].m),zero);assert.equal(raw(path[3].m),zero);
  assert.equal(source.slot,'U');assert.equal(raw(source.m),word);
  assert.deepEqual([source.l,source.s1,...[32,35,41].map(i=>source.r[i])],[1,6,5,0,5]);
  assert.equal(raw(es[si+1].otherChips[4].r,0),word);
  assert.deepEqual(es.slice(wi,wi+3).map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [[0x4E,'X'],[0x2A,'Y'],[0x39,'Z']]);
  const expected=structuredClone(es[wi].ring);
  for(let j=0;j<12;j++){expected.X[1+3*j]=writer.r[3*j];expected.Y[1+3*j]=writer.m[1+3*j];}
  assert.deepEqual(es[wi+2].ring,expected);
  const pair=r.traced.writes.filter(w=>w.command>=es[wi].command&&w.command<es[wi+2].command);
  assert.equal(pair.length,24);assert.ok(pair.every(w=>w.chip===4&&['X','Y'].includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
  checkStore(r,prefix+'save-u',word);
  for(let i=1;i<=4;i++) {
    const bi=es.findIndex(e=>e.stage===prefix+'remove-marker-'+i&&e.ip===0xE7&&e.s1===8&&e.sp[0]===0xA8);
    const block=checkSwapBlock(r,bi,4);assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);
    assert.equal(raw(block.body[0].r,0),zero);
  }
  assert.equal(raw(at(r,'keep-u-in-a').ring.control,0),word);
}

function checkDirect(r,prefix,word,source,lifts) {
  const es=r.traced.events;checkStore(r,prefix+'save-v-direct',word,source);
  for(const label of [...Array.from({length:lifts},(_,i)=>'lift-marker-'+(i+1)),
    ...Array.from({length:4-lifts},(_,i)=>'remove-marker-'+(i+1))]) {
    const index=es.findIndex(e=>e.stage===prefix+label&&e.ip===0xE7&&e.s1===8&&e.sp[0]===0xA8);
    const block=checkSwapBlock(r,index,4);
    assert.deepEqual(block.body.map(e=>e.slot),['X','Y','Z','T']);assert.equal(raw(block.body[0].r,0),zero);
  }
}

function check(r,{post=true,negative=false,secondaryW=false,uGuard=false}={}) {
  const oldMs=numeric(r.before),oldBank=r.beforeRegisters.slice(0,4);
  const written=negative&&r.options.forwardWrites?oldBank.slice().reverse():oldBank.slice();
  if(negative&&r.options.skipSaveP3)written[3]=r.beforeRegisters[14];
  assert.deepEqual(r.after,{...r.before,...Object.fromEntries(lower.map((n,i)=>[n,r.before[n].slice(0,2)+written[i]]))},
    'old ordinary bank is now in Ms, with original service fields and complete upper half');
  assert.deepEqual(r.afterRegisters,[...oldMs,...r.beforeRegisters.slice(4,9),
    written[0],...oldMs,r.options.skipSaveP3?r.beforeRegisters[14]:oldBank[3]],
    'old Ms is now in P0..P3; P4..P8 retained; every scratch output declared');
  const es=r.traced.events,writes=r.traced.writes;
  const readStart=at(r,'read-u/clear-before'),qStart=at(r,'read-last/exchange-wq/clear-before');
  assert.equal(raw(readStart.ring.Q,0),zero);
  assert.equal(raw(readStart.ring.T,0),r.options.skipSaveP3?r.beforeRegisters[14]:oldBank[3]);
  for(let i=0;i<3;i++)assert.equal(raw(readStart.ring[m1[i]],0),oldBank[i]);
  const stableUntil=secondaryW?at(r,'read-w/clear-before'):qStart;
  assert.deepEqual(writes.filter(w=>w.command>=readStart.command&&w.command<stableUntil.command&&
    [...lower,...upper].includes(w.slot)&&w.nibble%3===1&&w.before!==w.value),[],
    'nondestructive readers do not change even one Ms tetra, including transient states');
  if(secondaryW) {
    const wEnd=uGuard?at(r,'prepare-q/clear-before'):qStart;
    assert.ok(writes.filter(w=>w.command>=stableUntil.command&&w.command<wEnd.command&&
      [...lower,...upper].includes(w.slot)&&w.nibble%3===1&&w.before!==w.value)
      .every(w=>w.slot==='V'&&w.nibble<=34),'secondary W may change only the already backed-up V');
    for(const n of ['U','W','Q'])assert.equal(raw(wEnd.ring[n]),r.before[n].slice(2));
    assert.equal(raw(wEnd.ring.X,0),r.before.V.slice(2),'B retains original V despite its permitted Ms overwrite');
  }
  assert.deepEqual(writes.filter(w=>upper.includes(w.slot)&&w.nibble%3===1&&w.before!==w.value),[],
    'upper half of Ms never changes, even temporarily');
  assert.deepEqual(writes.filter(w=>m1.slice(4,9).includes(w.slot)&&w.nibble%3===0&&w.nibble<=33&&w.before!==w.value),[],
    'ordinary P4..P8 never change, even temporarily');
  const beginOutput=at(r,'output-0');
  assert.deepEqual(writes.filter(w=>w.command<beginOutput.command&&m1.slice(0,3).includes(w.slot)&&
    w.nibble%3===0&&w.nibble<=33&&w.before!==w.value),[],'old P0..P2 survive until all four Ms writes finish');
  assert.deepEqual([10,11,12,13].map(i=>raw(beginOutput.ring[m1[i]],0)),oldMs);
  checkU(r);checkDirect(r,'read-v/',oldMs[1],'V',2);
  const wOverlap=secondaryW?checkSecondaryWRead(r,'read-w/',oldMs[2],'keep-w-in-c'):
    (checkDirect(r,'read-w/',oldMs[2],'W',3),undefined);
  const overlap=checkQRead(r,'read-last/',oldMs[3],'keep-q-in-d');
  for(const [key,index] of [['В↑',3],['2',2],['1',1],['0',0]])
    checkLowerPush(r,'write-'+key+'/',index===3&&r.options.skipSaveP3?r.beforeRegisters[14]:oldBank[index]);
  // Restoring P3 happens last: all hidden operations have already returned.
  assert.equal(raw(at(r,'output-3').ring.Q,0),zero);
  const finalClear=at(r,'clear-final');
  assert.equal(raw(finalClear.ring.Q,0),oldMs[3]);
  assert.ok(es.every(e=>e.command<finalClear.command||e.ip!==0xD4));
  if(post)ordinaryChecks(r);
  return secondaryW?{overlap,wOverlap}:{overlap};
}

const complex={bank:['-8.7654321E23','-1E-99','-1.2345678E-42','9.8765432E99'],
  values:['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'],
  fullUpper:['3.2109876E-19','-1E-99','1.2345678E-42','-9.8765432E17']};
const cases=[{},...[0,1,2].map(phaseOffset=>({...complex,phaseOffset})),
  {...complex,settleFrames:12,markerFrames:8},{bank:['0','0','0','0'],values:['0','0','0','0']}];
function release(r){r.traced.events.length=0;r.traced.writes.length=0;}
const negativeValues=['-1E-99','-1.2345678E-42','-9.8765432E99','-1E-99'];
function checkNegativeURoute(r) {
  const words=numeric(r.before),old=r.beforeRegisters,copies=[words[0],words[1],zero,words[3]];
  assert.equal(r.options.phaseOffset,2);assert.equal(words[0],'901910000000');
  assert.deepEqual(r.after,{...r.before,...Object.fromEntries(lower.map((n,i)=>[n,r.before[n].slice(0,2)+old[i]]))});
  assert.deepEqual(r.afterRegisters,[...copies,...old.slice(4,9),old[0],...copies,old[3]]);
  checkU(r);checkDirect(r,'read-v/',words[1],'V',2);
  const stage='read-w/save-v-direct',control=rows(r,stage).find(e=>e.ip===0x9C&&e.slot==='U');
  assert.ok(control);assert.equal(control.nextIp,0x9E);assert.equal(control.raw,words[0]);
  const source=rows(r,stage).find(e=>e.ip===0xEE);
  assert.equal(source.slot,'X');assert.equal(source.raw,zero);assert.ok(source.command>control.command);
  checkStore(r,stage,zero);
  const qStart=at(r,'read-last/exchange-wq/clear-before');
  assert.equal(raw(qStart.ring.Y,0),zero,'C contains the wrong readout before Q is read');
  assert.equal(raw(qStart.ring.W),words[2],'the genuine W still exists in Ms when its copy is already wrong');
  assert.deepEqual(r.traced.writes.filter(w=>w.command<qStart.command&&[...lower,...upper].includes(w.slot)&&
    w.nibble%3===1&&w.before!==w.value),[],'failure is source selection, not an earlier Ms write');
  const overlap=checkQRead(r,'read-last/',words[3],'keep-q-in-d');
  for(const [key,index] of [['В↑',3],['2',2],['1',1],['0',0]])checkLowerPush(r,'write-'+key+'/',old[index]);
  ordinaryChecks(r);
  return {control:control.command,source:source.command,overlap};
}
function negativeURoute() {
  const r=p.run({phaseOffset:2,values:negativeValues});
  console.log('PASS negative-U native route:',JSON.stringify(checkNegativeURoute(r)),
    '9C(U)->9E; EE reads X=0, D4 stores it in P9, C backs it up; original W is still in Ms until overwritten by the outgoing bank. Arithmetic and program still work.');
  release(r);
}
function negativeU() {
  const scenarios=[...[0,2].map(phaseOffset=>({phaseOffset,values:negativeValues})),
    {phaseOffset:1,values:['11','22','33','-1.2345678E-42']}];
  for(const o of scenarios) {
    const r=p.runUnobserved(o),words=numeric(r.before),old=r.beforeRegisters;
    const copies=words.slice();
    if(o.phaseOffset===0)copies[3]=words[2];
    if(o.phaseOffset===2)copies[2]=zero;
    assert.deepEqual(r.after,{...r.before,...Object.fromEntries(lower.map((n,i)=>[n,r.before[n].slice(0,2)+old[i]]))});
    assert.deepEqual(r.afterRegisters,[...copies,...old.slice(4,9),old[0],...copies,old[3]]);
    assert.deepEqual(r.afterProgram,r.beforeProgram);
    if(o.phaseOffset!==1)assert.notDeepEqual(copies,words);
    console.log('PASS negative-U boundary (unobserved functional check):',JSON.stringify(o),JSON.stringify({copies,expected:words,
      outgoingBankCorrect:true,programTextHeld:true}));
  }
  console.log('LIMIT: the two failing negative-U examples preserve the outgoing bank but lose incoming Q or W; one successful negative-U input is not universality. These endpoint checks alone do not localize the failed ROM transition; a separate native trace covers phase 2.');
}
function controls(expectedDigest) {
  assert.match(expectedDigest??'',/^[0-9a-f]{64}$/);
  const {fullMsPages}=require('./probe_c8_payload.cjs'),{registers,program}=require('./probe_a8_ms_readout.cjs');
  const plain=p.prepare(),originalMs=fullMsPages(plain),originalBank=registers(plain),originalProgram=program(plain);
  p.finish(plain);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),expectedDigest);console.log('PASS observed/unobserved full core:',expectedDigest);
  // Not a new fixture: swap the result back on the SAME calculator.
  const back=p.runPrepared(plain,{phaseOffset:1});
  check(back);
  assert.deepEqual(back.after,originalMs);assert.deepEqual(back.afterRegisters.slice(0,9),originalBank.slice(0,9));
  assert.deepEqual(back.afterProgram,originalProgram);release(back);
  console.log('PASS second exchange restores all 8 Ms words, P0..P8 and program; scratch P9..E is NOT claimed restored.');
  for(const options of [{skipSaveP3:true},{forwardWrites:true}]) {
    const bad=p.run(options);check(bad,{negative:true});assert.notDeepEqual(numeric(bad.after),bad.beforeRegisters.slice(0,4));
    console.log('PASS negative control:',JSON.stringify(options),JSON.stringify(p.brief(bad)));release(bad);
  }
  negativeU();
  negativeURoute();
}
function main() {
  if(process.env.MS_LOWER_EXCHANGE_NEGATIVE_U_ONLY==='1')return negativeU();
  if(process.env.MS_LOWER_EXCHANGE_NEGATIVE_U_TRACE_ONLY==='1')return negativeURoute();
  if(process.env.MS_LOWER_EXCHANGE_CONTROLS_ONLY==='1')return controls(process.env.MS_LOWER_EXCHANGE_EXPECTED_DIGEST);
  const from=Number(process.env.MS_LOWER_EXCHANGE_FROM??0),count=Number(process.env.MS_LOWER_EXCHANGE_CASES??cases.length);
  let firstDigest;const overlaps=new Set();
  for(const o of cases.slice(from,from+count)) {
    const r=p.run(o),d=digest(r.calc);if(from===0)firstDigest??=d;
    const path=check(r);overlaps.add(path.overlap);
    console.log('PASS lower exchange:',JSON.stringify(o),JSON.stringify(path));console.log('OBSERVED_DIGEST',d);release(r);
  }
  console.log('COVERAGE',JSON.stringify({from,count:Math.min(count,cases.length-from),overlaps:[...overlaps],firstDigest}));
  if(from||count<cases.length)return;controls(firstDigest);
  console.log('LIMIT: native-tested conditional four-pair exchange using P9..E scratch, NOT whole-bank K1 or universal numeric/timing proof.');
}
if(require.main===module)main();
module.exports={check,checkU,checkDirect,checkStore,complex,cases,release,negativeU,checkNegativeURoute,negativeURoute,controls};
