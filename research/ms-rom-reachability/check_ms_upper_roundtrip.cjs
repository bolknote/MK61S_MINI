#!/usr/bin/env node
'use strict';
// Full native upper-half read/restore with a lower-Ms lifetime buffer.
// No callback changes execution based on observed contents.
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_roundtrip.cjs');
const readChecks=require('./check_ms_upper_read4.cjs');
const {compactPath}=require('./check_ms_read6_exit.cjs');
const {checkUpperPush,checkRotation}=require('./check_ms_upper_write.cjs');
const {checkExit:checkZeroExit}=require('./check_ms_zero_reuse.cjs');
const {checkLowerPush}=require('./check_ms_read6_roundtrip.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const names=['U','V','W','Q','P7','P8','P9','P10'],upper=names.slice(4);
const m1=['U','V','W','Q','P7','P8','P9','P10','marker','control','X1','X','Y','Z','T'];
const zero='000000000000',marker='0000F0000000',guard='958912345678';
const rows=(r,label)=>r.traced.events.filter(e=>e.stage===label);
const at=(r,label)=>{const e=rows(r,label).find(e=>e.ring);assert.ok(e,'stage '+label);return e;};
const nums=ring=>upper.map(n=>raw(ring[n]));
function held(r,from,to,indices) {
  const first=at(r,from).command,last=at(r,to).command;
  const slots=indices.map(i=>m1[i]);
  assert.ok(r.traced.writes.filter(w=>w.command>=first&&w.command<last&&slots.includes(w.slot)&&w.nibble%3===0&&w.nibble<=33)
    .every(w=>w.value===w.before),'ordinary payloads retained throughout '+from+'..'+to);
}
function untouchedUpper(r,from,to) {
  const first=at(r,from),last=at(r,to);
  assert.deepEqual(nums(last.ring),nums(first.ring));
  assert.ok(r.traced.writes.filter(w=>w.command>=first.command&&w.command<last.command&&upper.includes(w.slot)&&w.nibble%3===1)
    .every(w=>w.value===w.before),'buffer operation never changes an upper Ms numeric tetra');
}

function checkReader(r) {
  const es=r.traced.events,words=upper.map(n=>r.before[n].slice(2)),paths=[];
  const endLabels=['read-four/save-fifth','read-four/save-seventh','zero-before-write'];
  for(let i=0;i<3;i++) {
    const prefix='read-four/read-'+i+'/',begin=at(r,prefix+'prepare-zero-p8'),end=at(r,endLabels[i]);
    assert.deepEqual(nums(begin.ring).slice(1),[...words.slice(i+1),...Array(i).fill(guard)]);
    checkLowerPush(r,prefix+'zero-u/',zero);
    assert.equal(raw(begin.ring.U),zero,'every reader entry explicitly clears lower U');
    if(i===0)readChecks.checkCopy(r,prefix+'upper-copy-fifth',words[0],'marker');
    const prime=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'upper-prime'&&e.ip===0xE7&&e.slot==='P7'),1);
    assert.equal(raw(prime.body[0].r,0),guard);
    const rotation=checkRotation(r,prefix+'upper-swap');
    const capture=compactPath(es,prefix+'upper-after-0',{capture:true});
    readChecks.checkCopy(r,prefix+'upper-after-0',words[i+1],'X1');
    const post=readChecks.checkExit(r,prefix);paths.push({capture:capture.start,post:post.start});
    assert.deepEqual(nums(end.ring).slice(1),[...words.slice(i+2),...Array(i+1).fill(guard)]);
    assert.ok([guard,words[i+1]].includes(raw(end.ring.P7)));
    assert.ok(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&upper.slice(1).includes(w.slot)&&w.nibble%3===1&&w.value!==w.before)
      .every(w=>w.command>=rotation.start&&w.command<rotation.end));
  }
  const handoff=at(r,'zero-before-write').ring;
  for(const [index,word] of [[1,0],[6,1],[11,2],[10,3]])assert.equal(raw(handoff[m1[index]],0),words[word]);
  assert.equal(raw(handoff.Q,0),zero);
  held(r,'read-four/save-sixth','zero-before-write',[1]);
  held(r,'read-four/read-1/zero-source','zero-before-write',[1,6]);
  held(r,'read-four/read-2/zero-source','zero-before-write',[1,6,11]);
  return paths;
}

function checkWriter(r,prefix,next,source,index) {
  const begin=at(r,prefix+'prepare-zero-p8'),end=at(r,next),old=nums(begin.ring);
  for(const label of ['upper-copy-fifth','upper-prime','upper-swap'])assert.equal(rows(r,prefix+label).length,0);
  const seed=checkSwapBlock(r,r.traced.events.findIndex(e=>e.stage===prefix+'shift-0'&&e.ip===0xE7&&e.slot==='U'),4);
  assert.equal(raw(seed.body[0].r,0),zero);assert.equal(raw(seed.after.ring.V),marker);
  const push=checkUpperPush(r,prefix+'upper-after-0',source,{sourceIndex:index});
  const exit=checkZeroExit(r,prefix);
  assert.deepEqual(nums(end.ring),[source,...old.slice(0,3)],'pure upper push, without a guard replacement or rotation');
  assert.deepEqual(['U','V','W','Q'].map(n=>raw(end.ring[n])),[zero,guard,raw(begin.ring.U),raw(begin.ring.V)],
    'the entry carries the old lower V into lower Q without altering its twelve numeric tetras');
  assert.ok(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&upper.includes(w.slot)&&w.nibble%3===1&&w.value!==w.before)
    .every(w=>w.command>=push.start&&w.command<push.end),'all upper changes occur in the checked 48-tetra push');
  held(r,prefix+'zero-p0',next,[1,3,10,11]);
  return {...exit,push:push.entry};
}

function checkQRead(r,prefix,source,returned) {
  const es=r.traced.events,swap=rows(r,prefix+'exchange-wq/shifted-swap');
  const si=swap.findIndex(e=>e.otherChips?.[4].ip===0x4E&&e.otherChips[4].slot==='W');assert.ok(si>=0);
  const pair=swap.slice(si,si+3),original=pair[0].ring,swapped=structuredClone(original);
  assert.equal(raw(original.Q),source);assert.equal(raw(pair[0].otherChips[4].r,0),source);
  assert.deepEqual(pair.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x4E,'W'],[0x2A,'Q'],[0x39,'P7']]);
  for(let j=0;j<12;j++){swapped.W[1+3*j]=original.Q[1+3*j];swapped.Q[1+3*j]=original.W[1+3*j];}
  assert.deepEqual(pair[2].ring,swapped,'all 630 tetras after the buffer Q/W exchange');
  const sw=r.traced.writes.filter(w=>w.command>=pair[0].command&&w.command<pair[2].command);
  assert.equal(sw.length,24);assert.ok(sw.every(w=>w.chip===4&&['W','Q'].includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
  return checkSecondaryWRead(r,prefix+'read-q/',source,returned);
}

function checkSecondaryWRead(r,prefix,source,returned) {
  const es=r.traced.events,read=rows(r,prefix+'shifted-swap');
  // The first 53(W) can still belong to the preceding 1/F/1 request.
  // Select the completed 5/0/5 request and prove its connected output,
  // rather than treating any visit to the source address as a readout.
  const wi=read.findIndex(e=>e.otherChips?.[4].ip===0x53&&e.otherChips[4].slot==='W'&&e.otherChips[4].r[32]===5);
  assert.ok(wi>=0);const sourceRead=read[wi];assert.equal(raw(sourceRead.otherChips[4].m),source);
  assert.deepEqual([sourceRead.otherChips[4].l,sourceRead.otherChips[4].s1,...[32,35,41].map(i=>sourceRead.otherChips[4].r[i])],[1,6,5,0,5]);
  const connected=read.slice(wi,wi+12);
  assert.deepEqual(connected.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),
    [[0x53,'W'],[0x4F,'Q'],[0x41,'P7'],[0x43,'P8'],[0x4D,'P9'],[0x60,'P10'],
      [0x37,'marker'],[0x27,'control'],[0x61,'X1'],[0x4E,'X'],[0x2A,'Y'],[0x39,'Z']]);
  assert.ok(connected.every((e,i)=>e.command===sourceRead.command+i));
  const output=connected[9],outRing=structuredClone(output.ring);
  assert.equal(raw(output.otherChips[4].r,0),source);
  for(let j=0;j<12;j++){outRing.X[1+3*j]=parseInt(source[11-j],16);outRing.Y[1+3*j]=output.ring.X[1+3*j];}
  assert.deepEqual(connected[11].ring,outRing,'the completed W request really writes its source to the visible stack');
  const ow=r.traced.writes.filter(w=>w.command>=output.command&&w.command<connected[11].command);
  assert.equal(ow.length,24);assert.ok(ow.every(w=>w.chip===4&&['X','Y'].includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
  const visible=['X','Y','Z','T'],firstRows=rows(r,prefix+'post-swap-0');
  const li=firstRows.findIndex(e=>e.ip===0xE7&&e.slot==='X'&&e.nextIp===0xA8);assert.ok(li>=0);
  const first=firstRows.slice(li,li+5),initial=first[0].ring,shifted=structuredClone(initial);
  assert.deepEqual(first.map(e=>[e.ip,e.slot]),[[0xE7,'X'],[0xA8,'Y'],[0xA8,'Z'],[0xA8,'T'],[0xA9,'U']]);
  assert.equal(raw(first[0].r,0),zero);assert.equal(raw(initial.X),source);assert.equal(raw(initial.Y),source);
  const overlap=first[1].otherChips[4].ip===0x4E&&first[1].otherChips[4].slot==='X';
  const out=overlap?[source,zero,source,raw(initial.Z)]:[zero,source,source,raw(initial.Z)];
  if(overlap) {
    assert.deepEqual([first[2].otherChips[4].ip,first[2].otherChips[4].slot],[0x2A,'Y']);
    assert.equal(raw(first[1].otherChips[4].r,0),source);
  }
  for(let n=0;n<4;n++)for(let j=0;j<12;j++)shifted[visible[n]][1+3*j]=parseInt(out[n][11-j],16);
  assert.deepEqual(first[4].ring,shifted,'exact interleaving of the first zero lift and final secondary output');
  const mixed=r.traced.writes.filter(w=>w.command>=first[0].command&&w.command<first[4].command);
  assert.equal(mixed.length,overlap?72:48);assert.equal(mixed.filter(w=>w.chip===3).length,48);
  assert.ok(mixed.every(w=>w.nibble%3===1&&w.nibble<=34&&(w.chip===3?visible.includes(w.slot):w.chip===4&&['X','Y'].includes(w.slot))));
  const second=checkSwapBlock(r,es.findIndex(e=>e.stage===prefix+'post-swap-1'&&e.ip===0xE7&&e.slot==='X'&&e.nextIp===0xA8),4);
  assert.equal(raw(second.body[0].r,0),zero);assert.deepEqual(visible.map(n=>raw(second.body[0].ring[n])),out);
  assert.equal(raw(second.after.ring.T),source,'T retains the source in both interleavings');
  for(let i=2;i<=4;i++) {
    const rr=rows(r,prefix+'post-swap-'+i);
    const ri=rr.findIndex(e=>e.otherChips?.[4].ip===0x3A&&e.otherChips[4].slot==='X');assert.ok(ri>=0);
    const block=rr.slice(ri,ri+5),old=block[0].ring,rotated=structuredClone(old);
    assert.deepEqual(block.map(e=>[e.otherChips[4].ip,e.otherChips[4].slot]),[[0x3A,'X'],[0x3A,'Y'],[0x3A,'Z'],[0x2A,'T'],[0x39,'U']]);
    for(let n=0;n<4;n++)for(let j=0;j<12;j++)rotated[visible[n]][1+3*j]=old[visible[(n+1)%4]][1+3*j];
    assert.deepEqual(block[4].ring,rotated);
    const writes=r.traced.writes.filter(w=>w.command>=block[0].command&&w.command<block[4].command);
    assert.equal(writes.length,48);assert.ok(writes.every(w=>w.chip===4&&visible.includes(w.slot)&&w.nibble%3===1&&w.nibble<=34));
    const next=at(r,prefix+(i===4?'save':'post-swap-'+(i+1))).ring;
    assert.deepEqual(visible.map(n=>raw(next[n])),visible.map(n=>raw(rotated[n])),'formatter preserves this visible rotation');
  }
  const save=rows(r,prefix+'save');
  const ee=save.find(e=>e.ip===0xEE&&e.slot==='X');assert.ok(ee);assert.equal(ee.raw,source);
  const di=es.findIndex(e=>e.stage===prefix+'save'&&e.ip===0xD4&&e.slot==='control');assert.ok(di>=0);
  const expected=structuredClone(es[di].ring);
  for(let j=0;j<12;j++)expected.control[3*j]=ee.m[1+3*j];
  assert.equal(es[di+1].ip,0xA5);assert.deepEqual(es[di+1].ring,expected);
  const dw=r.traced.writes.filter(w=>w.command===es[di].command);
  assert.equal(dw.length,12);assert.ok(dw.every(w=>w.chip===3&&w.slot==='control'&&w.nibble%3===0&&w.nibble<=33));
  assert.equal(raw(at(r,returned).ring.control,0),source);
  return overlap;
}

function check(r) {
  assert.ok(!r.options.skipBridge&&!r.options.reverseFirstTwo);
  const words=upper.map(n=>r.before[n].slice(2)),[a,b,c,d]=words;
  const reads=checkReader(r);
  checkLowerPush(r,'clean-entry-u/',zero);
  const first=at(r,'push-d/zero-p0').ring;assert.equal(raw(first.V,0),a);assert.equal(raw(first.Q,0),b);
  assert.equal(raw(first.X,0),c);assert.equal(raw(first.X1,0),d);
  const writes=[checkWriter(r,'push-d/','push-c/zero-p0',d,10),checkWriter(r,'push-c/','park-d/save-b',c,11)];
  checkLowerPush(r,'park-d/d-to-u/',d);checkLowerPush(r,'park-d/d-to-v/',zero);
  const parked=at(r,'b-to-a').ring;assert.equal(raw(parked.V),d);assert.equal(raw(parked.U),zero);assert.equal(raw(parked.Q,0),b);
  untouchedUpper(r,'park-d/save-b','b-to-a');held(r,'park-d/save-b','b-to-a',[1,10,11]);
  assert.equal(raw(at(r,'park-d/d-to-p9').ring.T,0),b);
  writes.push(checkWriter(r,'push-b/','bridge-d/save-q-backup',b,10));
  assert.equal(raw(at(r,'bridge-d/save-q-backup').ring.Q),d);
  const overlap1=checkQRead(r,'bridge-d/',d,'bridge-d/put-v-in-u/clear-before');
  assert.equal(raw(at(r,'bridge-d/put-v-in-u/clear-before').ring.T,0),b);
  checkLowerPush(r,'bridge-d/put-v-in-u/',d);checkLowerPush(r,'bridge-d/move-v-to-v/',zero);
  const restored=at(r,'a-to-a').ring;assert.equal(raw(restored.V),d);assert.equal(raw(restored.U),zero);assert.equal(raw(restored.Q,0),b);
  untouchedUpper(r,'bridge-d/save-q-backup','a-to-a');held(r,'bridge-d/save-q-backup','a-to-a',[1,10,11]);
  writes.push(checkWriter(r,'push-a/','finish-d/save-b',a,10));
  assert.deepEqual(nums(at(r,'finish-d/save-b').ring),words);
  assert.equal(raw(at(r,'finish-d/save-b').ring.Q),d);
  const overlap2=checkQRead(r,'finish-d/',d,'finish-d/d-to-p6');
  assert.equal(raw(at(r,'finish-d/d-to-p6').ring.T,0),b);
  for(let i=0;i<4;i++)checkLowerPush(r,'finish-d/clear-lower-'+i+'/',zero);
  untouchedUpper(r,'finish-d/save-b','done');held(r,'finish-d/save-b','done',[1,10,11]);
  held(r,'finish-d/zero-source','done',[6]);
  assert.deepEqual(r.after,Object.fromEntries(names.map(n=>[n,r.before[n].slice(0,2)+(upper.includes(n)?r.before[n].slice(2):zero)])),
    'all four complete upper Ms words restored; lower numeric half explicitly cleared; every service field preserved');
  const ptr=rows(r,'push-a/upper-after-4').find(e=>e.ip===0xD6);
  assert.deepEqual(r.afterRegisters,[zero,a,marker,b,guard,'007000000007',d,
    ptr.slot==='P10'?'007000000009':'000090000000',zero,zero,a,c,
    writes[3].post==='U'?'007000000000':'000070000000','007000000010',b],
    'all 15 ordinary words, including all four retained original upper copies');
  held(r,'push-d/zero-p0','done',[1,11]);
  readChecks.ordinaryChecks(r);
  return {reads,writes: writes.map(x=>({push:x.push,post:x.post,zeros:x.zeros})),overlaps:[overlap1,overlap2]};
}
function checkNegative(r,order=false) {
  const [a,b,c,d]=upper.map(n=>r.before[n].slice(2));
  const expected=order?[a,b,d,c]:[a,b,c,d];
  assert.deepEqual(upper.map(n=>r.after[n].slice(2)),expected);
  assert.deepEqual(names.slice(0,4).map(n=>r.after[n].slice(2)),Array(4).fill(zero));
  assert.deepEqual([1,3,11,6].map(i=>r.afterRegisters[i]),[a,b,c,order?d:guard]);
  if(!order) {
    assert.equal(raw(at(r,'a-to-a').ring.Q),d,'the missing bridge left the good d copy in Q');
    assert.equal(raw(at(r,'finish-d/save-b').ring.Q),guard,'the next entry overwrote it with former V');
  }
  readChecks.ordinaryChecks(r);
}
const complex=readChecks.cases[0];
const cases=[...[0,1,2].map(phaseOffset=>({...complex,phaseOffset})),
  {...readChecks.cases[3],initialU:'-1E-99',initialP3:'-7.654321E23'},
  {...readChecks.cases[4],initialP3:'1.2345678E-42'},
  readChecks.cases[5],readChecks.cases[6],readChecks.cases[7]];
function release(r){r.traced.events.length=0;r.traced.writes.length=0;}
function main() {
  const from=Number(process.env.MS_UPPER_ROUND_FROM??0),limit=Number(process.env.MS_UPPER_ROUND_CASES??cases.length);
  const controlsOnly=process.env.MS_UPPER_ROUND_CONTROLS_ONLY==='1';
  let firstDigest=controlsOnly?process.env.MS_UPPER_ROUND_EXPECTED_DIGEST:undefined;
  const pushes=new Set(),posts=new Set(),zeros=new Set(),overlaps=new Set(),captures=new Set(),readPosts=new Set();
  if(!controlsOnly)for(const o of cases.slice(from,from+limit)) {
    const r=p.run(o),observed=digest(r.calc);firstDigest??=observed;
    const paths=check(r);
    paths.writes.forEach(x=>{pushes.add(x.push);posts.add(x.post);x.zeros.forEach(z=>zeros.add(z));});
    paths.reads.forEach(x=>{captures.add(x.capture);readPosts.add(x.post);});paths.overlaps.forEach(x=>overlaps.add(x));
    console.log('PASS upper roundtrip:',JSON.stringify(o),JSON.stringify(paths));console.log('OBSERVED_DIGEST',observed);release(r);
  }
  if(!controlsOnly) {
    console.log('COVERAGE',JSON.stringify({from,count:Math.min(limit,cases.length-from),pushes:[...pushes].sort(),posts:[...posts].sort(),
      zeros:[...zeros].sort(),captures:[...captures].sort(),readPosts:[...readPosts].sort(),overlaps:[...overlaps].sort(),firstDigest}));
    if(from||limit<cases.length)return;
    assert.deepEqual([...captures].sort(),['P8','Y']);assert.deepEqual([...readPosts].sort(),['U','Y']);
    assert.deepEqual([...overlaps].sort(),[false,true]);
    // In this full schedule the four writer preparations converge to P9/U,
    // even when the initial reader phase or waits differ. Do not claim the
    // separate writer's Z/Y branches were reached merely because its checker
    // supports them. The complete observed path sets are reported above.
    assert.ok(pushes.has('P9')&&posts.has('U')&&zeros.has('P8'));
  }
  assert.match(firstDigest??'',/^[0-9a-f]{64}$/);
  const plain=p.prepare(cases[0]);p.finish(plain,cases[0]);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),firstDigest);console.log('PASS observed/unobserved whole core:',firstDigest);
  const repeated=p.runPrepared(plain,{phaseOffset:1});check(repeated);release(repeated);
  console.log('PASS full repeat without reset, state import, fixture setup or ordinary-register reseeding.');
  const lost=p.run({...complex,skipBridge:true});checkNegative(lost);release(lost);
  console.log('PASS negative control: omit the d bridge; upper Ms is restored and arithmetic works, but the fourth retained copy is the guard.');
  const order=p.run({...complex,reverseFirstTwo:true});checkNegative(order,true);release(order);
  console.log('PASS negative control: reverse the first two sources; four readouts remain right but the final upper tail is swapped.');
  console.log('LIMIT: upper-half read/restore; lower Ms explicitly cleared, ordinary scratch overwritten. NOT whole-Ms restoration, eight simultaneous copies or K1.');
}
if(require.main===module)main();
module.exports={check,checkReader,checkWriter,checkQRead,checkSecondaryWRead,checkNegative,cases};
