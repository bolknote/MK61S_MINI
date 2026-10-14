#!/usr/bin/env node
'use strict';
// SOURCE-selected marker-constructor controls, not a key sweep. The supplied
// Puhov recipe distinguishes younger2zero and older7zero blanks; the existing
// stock-reference probe also records the logical blank recipe. Try only those
// exact recipes and their documented UP/R9/fiveUP storage tail. Public keys
// only, preexisting arithmetic R9, fresh unobserved ALL5 mirrors, no setters.
// The minimal STOP constructor and source-derived raw-reader follow-ups now
// produce exact F in W and Q. The earlier Q recipe has extra T/V; the later
// isolated-Q variant removes them. Neither is a complete K2 entry.
// 'clear-real'/realRemoved are historical probe labels:
// in the positive bare-F route RCL0 shifts Z to T but DOES NOT remove aux0.
// The zero-source + READ2/READ2 variant now isolates Q: it prevents V/F and
// removes T via X1 while holding Q and the original aux0 marker. P2=0 is a
// premise, and the prepared0/2/D/data/phase exchange entry is still missing.
// A source-selected header6 carrier now copies P8 -> hiddenP10, and a real
// program erases P8 before reading hiddenP10 -> ordinaryP9. These are raw
// copies, not a number decoder, arbitrary-old-bank preservation or K2.
// After marker cleanup, NORMAL P6 numbers can be stored in P10 through ENTER,
// with X/P6 cleared and a real STOP/idle, then recovered into P9/display.
// It remains a relocated stack, not an independent normal-geometry register.
// Further source-selected restore profiles erase falseQ/P9 holding the normal
// P10 word, then move Z/U markers to T. Native arithmetic still errors. The
// full-key value audits are passive only, never keyboard/phase feedback.
const assert=require('node:assert/strict');
const {setup,arithmetic,aligned,dump,rawRegister,sample,hashes}=
  require('./cache-bc-head93-indirect-ghost-native.cjs');
const {initialTags}=require('./cache-bc-head93-native-carriers.cjs');
const chips=[null,'ir2a','ir2b','ik1302','ik1303','ik1306'];
const fullState=c=>Object.fromEntries(chips.slice(1).map(name=>{
  const p=c[name];return [name,{m:p.memory.slice(),tick:p.tickIndex,input:p.input,output:p.output,
    ...(name.startsWith('ik')?{r:p.r.slice(),st:p.stack.slice(),s:p.s,s1:p.s1,l:p.l,t:p.t,
      carry:p.carry,keyX:p.keyX,keyY:p.keyY}:{})}];
}));
const fullTags=t=>Object.fromEntries(chips.slice(1).map((name,i)=>[name,t[i+1].slice()]));
const slots={X:[5,34],Y:[4,34],Z:[3,34],T:[2,118],X1:[2,160],
  U:[2,202],V:[2,244],W:[2,34],Q:[2,76],
  'Ms:P7':[1,118],'Ms:P8':[1,160],'Ms:P9':[1,202],'Ms:P10':[1,244],
  aux0:[1,34],aux1:[1,76]};
const raw=(c,chip,end)=>Array.from({length:12},(_,i)=>
  c.memoryForChip(chip)[end-3*i].toString(16).toUpperCase()).join('');
function snapshot(c) {
  assert.equal(c.ir2a.tickIndex,84);
  const words=Object.fromEntries(Object.entries(slots).map(([n,[chip,end]])=>[n,raw(c,chip,end)]));
  return {words,markers:Object.keys(words).filter(n=>words[n][4]==='F'),
    display:c.displayText(),pc:c.programCounter(),pcRaw:[c.ik1302.r[34],c.ik1302.r[31]],
    ...sample(c),modeR2:c.ik1302.r[2],
    R9:rawRegister(c,9),program:Array.from({length:105},(_,i)=>c.readCommand(i)),
    registers:Array.from({length:15},(_,i)=>rawRegister(c,i))};
}
function press(c,keys) {
  for(const key of keys)c.press(key).runFrames(12);
  return aligned(c);
}
function run(name,recipe,{transport=null}={}) {
  hashes();const c=setup(false,'10'),plain=setup(false,'10');
  assert.deepEqual(dump(c),dump(plain));const before=snapshot(c);
  assert.equal(before.R9,'600010000003');
  for(const x of [c,plain])press(x,recipe);
  assert.deepEqual(dump(c),dump(plain));const blank=snapshot(c);
  let saved=null;
  if(transport) {
    const transfer=transport==='swapY'?['↔']:transport==='lastX'?['F','Сx']:null;
    assert.ok(transfer,'source-selected Y/lastX transfer only');
    for(const x of [c,plain])press(x,[...transfer,'X→П','9']);
    assert.deepEqual(dump(c),dump(plain));saved=snapshot(c);
    for(const x of [c,plain])press(x,['Сx','0','0','/','ВП','K','0']);
    assert.deepEqual(dump(c),dump(plain));
  }
  const store=['В↑','П→X','9',...Array(5).fill('В↑')];
  for(const x of [c,plain])press(x,store);
  assert.deepEqual(dump(c),dump(plain));const after=snapshot(c);
  const report={case:name,recipe,transport,store,blank,saved,after,
    ordinaryChanged:after.registers.flatMap((v,i)=>v===before.registers[i]?[]:[i]),
    programChanged:after.program.flatMap((v,i)=>v===before.program[i]?[]:[i]),
    nativeQMarkerF:after.words.Q[4]==='F',ALL5mirror:true,onlyPublicKeys:true};
  assert.equal(report.nativeQMarkerF,false);
  assert.deepEqual(report.programChanged,[]);
  assert.deepEqual(report.ordinaryChanged,transport?[9]:[]);
  if(transport)assert.equal(saved.R9,'000000000000');
  else assert.equal(after.words.U,'600010000003');
  console.log(JSON.stringify(report));hashes();return report;
}
function arrowTransport() {
  hashes();const c=setup(false,'10'),plain=setup(false,'10');
  const recipe=['Сx','0','0','/','ВП','K','0'];
  for(const x of [c,plain])press(x,recipe);
  assert.deepEqual(dump(c),dump(plain));
  const stages=[{name:'blank',...snapshot(c)}];
  for(const x of [c,plain])press(x,['↔']);
  assert.deepEqual(dump(c),dump(plain));stages.push({name:'swap_to_X',...snapshot(c)});
  for(let i=0;i<7;i++) {
    for(const x of [c,plain])press(x,['В↑']);
    assert.deepEqual(dump(c),dump(plain));stages.push({name:'up'+(i+1),...snapshot(c)});
  }
  assert.equal(stages[1].words.X,'0010F0000000');
  assert.ok(stages.slice(1).every(s=>s.words.X==='0010F0000000'&&s.words.Q==='000000000000'));
  assert.ok(stages.every(s=>Object.entries(s.words).filter(([n])=>
    ['U','V','W','Q'].includes(n)||n.startsWith('Ms:')).every(([,v])=>v==='000000000000')));
  console.log(JSON.stringify({case:'physical_F_direct_sevenUP',recipe,stages,
    nativeQMarkerF:stages.some(s=>s.words.Q[4]==='F'),ALL5mirror:true,onlyPublicKeys:true}));
  hashes();return stages;
}
function stopTransport({fifo=false,zeros=2,minimal=false,proof=false,readBack=false,
  readAgainAfterClear=false,clearDigitLift=false,lastXLift=false,
  removeRealThenLastX=false,qReadInsteadLastX=false,qReadDigit='1',logical=false,
  headerAdjustedRecall=false,traceSeek=false,qIdleCheck=false,qWholeTail=false,
  qCleanup=null,qZeroSource=false,qFinalIdleCheck=false,qAddressRead=null,qReserveGhost8=false,
  ghostMultiplier='1.0000003',qAddressIdleCheck=false,qPayloadExit=null,
  qInverseScale=false,qReadbackIdleCheck=false,qPlainPayload=false,qNormalReserve=false,
  normalInput='12345678',qPlainControl=null,qNormalArithmeticCheck=false,
  qRestoreControl=null,qRestoreIdleCheck=false,qRestoreCalcCheck=false,
  qControllerZeroDigit='A',qControllerAck=false,qControllerClearDigit='5',
  qControllerZeroAfterCx=false,qControllerPostCxDigit='E',qControllerPostCalc=false,
  qTRecoveryProfile=null,qTLeadFrames=0,qTZeroDigit='E',qMarkerPacket=null,qMarkerRepeat=false,qMarkerRepeatClear=false,qMarkerRepeatCount=1,qMarkerLateNumber=null,qMarkerSecondPhase=null,log=true}={}) {
  assert.ok([1,2].includes(zeros),'two source-derived leading-zero cases only');
  assert.ok(!readAgainAfterClear||readBack,'second raw read requires a first read');
  assert.ok(!clearDigitLift||readAgainAfterClear,'digit lift requires the native W constructor');
  assert.ok(!lastXLift||readAgainAfterClear,'LastX follow-up requires the native W constructor');
  assert.ok(!removeRealThenLastX||(lastXLift&&!clearDigitLift),
    'the source-selected Z/W tail requires the undigitized W/LastX prefix');
  assert.ok(!headerAdjustedRecall||(logical&&readBack),
    'the source-derived minus-three counter correction applies only to the logical F context');
  assert.ok(!qReadInsteadLastX||(removeRealThenLastX&&!logical),
    'the source-derived Q reader candidates start at the native bare T/W state');
  assert.ok(['1','9'].includes(qReadDigit),'the two source-derived Q reader corrections only');
  assert.ok(!qIdleCheck||(qReadInsteadLastX&&qReadDigit==='9'),
    'idle stability control requires the actual positive Q constructor');
  assert.ok(!qWholeTail||(qReadInsteadLastX&&qReadDigit==='9'),
    'continuous01-to-BE audit requires the positive Q producer');
  assert.ok(qCleanup===null||['clear_v','clear_v_and_stack','read0_twice','read2_twice'].includes(qCleanup),
    'only the source-selected zero-writer/visible-push cleanup tails');
  assert.ok(qCleanup===null||(qReadInsteadLastX&&qReadDigit==='9'&&!fifo),
    'cleanup starts at the native positive T/V/Q state');
  assert.ok(!qZeroSource||(qReadInsteadLastX&&qReadDigit==='9'),
    'zero-source construction relies on the proven OLD W -> Q push');
  assert.ok(!qFinalIdleCheck||(qZeroSource&&qCleanup==='read2_twice'),
    'final stability audit requires the isolated-Q constructor');
  assert.ok(qAddressRead===null||['9','D','E'].includes(qAddressRead),
    'only source-derived relative-address controls, not a key sweep');
  assert.ok(qAddressRead===null||qFinalIdleCheck,'address controls start at isolatedQ');
  assert.ok(!qReserveGhost8||(minimal&&qFinalIdleCheck),
    'ghost8 reservoir belongs to a fresh minimal isolated-Q protocol');
  assert.ok(!qInverseScale||(qReserveGhost8&&ghostMultiplier==='1.2345678'),
    'inverse-scale reserve is the selected eight-digit payload protocol');
  assert.ok(!qPlainPayload||(qReserveGhost8&&!qInverseScale&&ghostMultiplier==='1.2345678'),
    'plain-number control uses the selected12345678 fixture only');
  assert.ok(!qNormalReserve||(qReserveGhost8&&!qInverseScale&&!qPlainPayload),
    'normal-number reservoir accompanies the source-derived header6 marker cleanup');
  const normalWords={'12345678':'007012345678','-87654321':'007987654321',
    '1.2345678E-50':'950012345678'};
  assert.ok(Object.hasOwn(normalWords,normalInput),'three selected ordinary-number fixtures, no key sweep');
  const normalWord=normalWords[normalInput];
  assert.ok(qPlainControl===null||['no_enter','no_swap'].includes(qPlainControl),
    'source-selected missing-store/missing-read negative controls only');
  assert.ok(qPlainControl===null||qPayloadExit==='plain_roundtrip');
  assert.ok(!qNormalArithmeticCheck||(qPayloadExit==='plain_roundtrip'&&qPlainControl===null
    &&normalInput==='12345678'),'selected ordinary add-one control follows successful integer readback');
  assert.ok(qRestoreControl===null||['seed','readF','readF2','lastX','eraseQ','plantZ','wipeQ','wipeQShort','noZ','noP9'].includes(qRestoreControl),
    'source-derived F-reservoir/first shifted recall controls, no key sweep');
  assert.ok(qRestoreControl===null||(minimal&&zeros===1&&qNormalReserve
    &&qPayloadExit==='plain_roundtrip'&&qPlainControl===null&&!qNormalArithmeticCheck
    &&!qReadbackIdleCheck),'restore control stops after real storage/idle, before readback');
  assert.ok(!qRestoreIdleCheck||qRestoreControl!==null,'restore idle follows an explicit native control');
  assert.ok(!qRestoreCalcCheck||(qRestoreIdleCheck&&(qRestoreControl==='wipeQShort'
    ||(qRestoreControl==='noP9'&&qControllerAck&&qControllerZeroDigit==='A'
      &&qControllerClearDigit==='5'))),
    'ordinary2/ENTER/3/+ follows Q erasure or the selected acknowledged P9 cleanup');
  assert.ok(['A','D'].includes(qControllerZeroDigit),
    'corrected relative source or the original wrong-source control only');
  assert.ok(!qControllerAck||qRestoreControl==='noP9');
  assert.ok(['5','E'].includes(qControllerClearDigit),'two source-selected last-reader address contexts');
  assert.ok(!qControllerZeroAfterCx||(qRestoreControl==='noP9'&&qControllerAck
    &&qControllerZeroDigit==='A'&&qControllerClearDigit==='5'&&qRestoreIdleCheck
    &&!qRestoreCalcCheck),'one source-selected R0-zero recall after U/V CX control priming');
  assert.ok(['8','E'].includes(qControllerPostCxDigit),
    'post-CX actual aux1-relative zero source or the prior U-relative negative control');
  assert.ok(!qControllerPostCalc||(qControllerZeroAfterCx&&qControllerPostCxDigit==='E'),
    'ordinary arithmetic diagnostic only after the selected realR0 zero shift');
  assert.ok(qTRecoveryProfile===null||['sign','zero','enter','lastx'].includes(qTRecoveryProfile),
    'source-selected E9/SIGN or fixed R0 four-word zero shift, no keyboard sweep');
  assert.ok(qTRecoveryProfile===null||(qControllerZeroAfterCx&&qControllerPostCxDigit==='E'),
    'T recovery follows native Q/P9/Z/U cleanup, not an imported fixture');
  assert.ok([0,2].includes(qTLeadFrames)&&(!qTLeadFrames||qTRecoveryProfile==='zero'),
    'one calculated lead-frame control uses real waiting, never a phase patch');
  assert.ok(['E','6'].includes(qTZeroDigit),
    'same aux1-relative zero sources: physicalR0 or physicalR7; no operand sweep');
  const packetRank=({u:1,q:2,q2:3,m1:4,m1a:5,m2:6,p8:6,xf:7,yf:8,yfd:8,yc:9,ycl:9,ys:10,ysl:10,ysr:11,ylx:12,yls:13,
    yf1:11,yf2:11,yf3:11,ynx:11,yns:11,ynr:11,ynb:11,yc1:11,yc6:11,yc6x:11,yc7:11,yc7z:11,ykc:11,ykm:11,ykn:11,ykr:11,yku:11,ykv:11})[qMarkerPacket]||0;
  const packetFlush=({yf1:1,yf2:2,yf3:3,ynx:3,yns:3,ynr:3,ynb:3,yc1:3,yc6:3,yc6x:3,yc7:3,yc7z:3,ykc:3,ykm:3,ykn:3,ykr:3,yku:3,ykv:3})[qMarkerPacket]||0;
  const packetCodes={'packet-seed8':0x4D,'packet-plant-u':0x6A,'packet-insert-q':0x65,
    'packet-insert-q-ack':0x65,'packet-move-q1':0x63,'packet-move-q1-ack':0x6A,
    'packet-move-q2':0x62,'packet-move-q2-A':0x6A,'packet-open-y':0x6E,
    'packet-shift-y':0x62,'packet-shift-y-old-address':0x6D,
    'packet-clear-u-prime':0x6C,'packet-clear-u':0x6C,
    'packet-sign':0x32,'packet-sign-retry':0x32,
    'packet-lastx':0x0F,'packet-sign-number':0x32,
    'packet-flush1':0x65,'packet-flush2':0x65,'packet-flush3':0x65,
    'packet-lastx-clean':0x0F,'packet-sign-clean':0x32,
    'packet-lastx-repeat':0x0F,'packet-sign-repeat':0x32,'packet-sign-overwrite':0x32,
    'packet-restore-aux0F':0x66,'packet-restore-clone1':0x60,'packet-restore-clone2':0x60,
    'packet-restore-TF':0x6B,'packet-restore-X1F':0x67,'packet-restore-removeP8':0x63,
    'packet-restore-cx':0x0D,'packet-restore-clearX1':0x6B,
    'packet-clean-zero1':0x65,'packet-clean-zero2':0x65,'packet-clean-zero3':0x65,'packet-clean-zero4':0x65,
    'packet-clean-aux0F':0x66,'packet-clean-port5':0x48,'packet-clean-YF':0x68,
    'packet-clean-X1F':0x6B,'packet-clean-P8':0x6E,
    'packet-clean-flush1':0x64,'packet-clean-flush2':0x64,'packet-clean-flush3':0x64,'packet-clean-flush4':0x64,'packet-clean-flush5':0x64,
    'packet-clean-port5-zero':0x45,'packet-clean-cx1':0x0D,'packet-clean-cx2':0x0D,
    'packet-clean-two':0x02,'packet-clean-enter':0x0E,'packet-clean-three':0x03,'packet-clean-plus':0x10,
    'packet-clean-store2':0x42,'packet-clean-register-clear':0x0D,'packet-clean-read2':0x62,
    'packet-clean-register-clear2':0x0D,'packet-clean-register-zero2':0x42,'packet-clean-lastx':0x0F,
    'packet-clean-backup-clear':0x0D,'packet-clean-backup-zero':0x4E,
    'packet-reopen-YF':0x6C,'packet-reopen-X1F':0x68,'packet-reopen-WF':0x6C,
    'packet-reopen-P8F':0x63,'packet-reopen-W0':0x64,'packet-reopen-aux0zero':0x69,
    'packet-reopen-Zzero':0x48,'packet-reopen-lastx':0x0F,
    'packet-reopen-aux0zero-native':0x61,'packet-reopen-flush1':0x65,
    'packet-reopen-flush2':0x65,'packet-reopen-flush3':0x65};
  assert.ok(qMarkerLateNumber===null||['2468','1.2345678E-50'].includes(qMarkerLateNumber),
    'two source-directed late writes by original numeric entry/E9 LastX, no key sweep');
  assert.ok(qMarkerLateNumber===null||(qMarkerPacket==='yku'&&qMarkerRepeat&&qMarkerRepeatClear&&normalInput==='12345678'),
    'late data follows the already proved integer geometry/ordinary backup erasure');
  const lateCodes={'Сx':0x0D,',':0x0A,'/-/':0x0B,'ВП':0x0C};
  const lateWords={'2468':'003024680000','1.2345678E-50':'950012345678'};
  const packetLateActions=qMarkerLateNumber===null?[]:[
    ['packet-late-clear',['Сx'],0x0D],
    ...Array.from(qMarkerLateNumber,(char,i)=>{
      const key=char==='.'?',':char==='E'?'ВП':char==='-'?'/-/':char;
      return ['packet-late-key'+(i+1),[key],lateCodes[key]??Number(key)];
    }),['packet-late-sign',['K','5'],0x32]];
  for(const [label,,code] of packetLateActions)packetCodes[label]=code;
  const packetRepeatTemplate=[
    ...Array.from({length:4},(_,i)=>['zero'+(i+1),['П→X','5'],0x65]),
    ['aux0F',['П→X','6'],0x66],['port5',['X→П','8'],0x48],
    ['YF',['П→X','8'],0x68],['X1F',['П→X','/-/'],0x6B],['P8',['П→X','В↑'],0x6E],
    ...Array.from({length:5},(_,i)=>['flush'+(i+1),['П→X','4'],0x64]),
    ['port5-zero',['X→П','5'],0x45],['cx',['Сx'],0x0D],['six',['6'],0x06],
    ['enter',['В↑'],0x0E],['seven',['7'],0x07],['plus',['+'],0x10],
    ['lastx',['F','В↑'],0x0F],['after-clear',['Сx'],0x0D],
    ...(qMarkerRepeatClear?Array.from({length:4},(_,i)=>['preclear'+(i+1),['П→X','0'],0x60]):[]),
    ['reopen-YF',['П→X','ВП'],0x6C],['reopen-X1F',['П→X','8'],0x68],
    ['reopen-WF',['П→X','ВП'],0x6C],['reopen-P8F',['П→X','3'],0x63],
    ['reopen-W0',['П→X','4'],0x64],['reopen-aux0zero',['П→X','1'],0x61],
    ['reopen-Zzero',['X→П','8'],0x48],
    ...Array.from({length:3},(_,i)=>['reopen-flush'+(i+1),['П→X','5'],0x65]),
    ['reopen-lastx',['F','В↑'],0x0F]
  ];
  assert.ok(qMarkerSecondPhase===null||['seed','p9-write','p9-source-write','p7-shift-write','p7-shift-clear','p7-shift-read','p7-first-frontier','p7-first-paced','p7-first-p9','p7-first-read','p8-normal','p8-normal-math','p8-reopen-control','p8-reopen-clear','p8-reopen-swap','p8-reopen-run-stop','p7-normal-retain','p7-normal-retain-math','p7-normal-retain-read','p7-normal-retain-both','p7-normal-retain-repeat','p7-normal-retain-write3','p7-normal-retain-restore3','p7-normal-retain-restore3-cx'].includes(qMarkerSecondPhase),'second-cell source-led preparation/writer');
  assert.ok(qMarkerSecondPhase===null||(qMarkerPacket==='yku'&&!qMarkerRepeat&&qMarkerLateNumber===null),
    'temporary first-number backup only in the dedicated second-cell preparation');
  const secondProgram=qMarkerSecondPhase==='p8-reopen-run-stop';
  const p7Repeat=qMarkerSecondPhase==='p7-normal-retain-repeat';
  const p7Restore3CX=qMarkerSecondPhase==='p7-normal-retain-restore3-cx';
  const p7Restore3=qMarkerSecondPhase==='p7-normal-retain-restore3'||p7Restore3CX;
  const p7Write3=qMarkerSecondPhase==='p7-normal-retain-write3'||p7Restore3;
  const secondRetain=['p7-normal-retain','p7-normal-retain-math','p7-normal-retain-read','p7-normal-retain-both'].includes(qMarkerSecondPhase)||p7Repeat||p7Write3;
  const secondNormal=['p8-normal','p8-normal-math','p8-reopen-control','p8-reopen-clear','p8-reopen-swap'].includes(qMarkerSecondPhase)||secondProgram||secondRetain;
  const firstP9=['p7-first-p9','p7-first-read'].includes(qMarkerSecondPhase)||secondNormal;
  const firstFrontier=['p7-first-frontier','p7-first-paced'].includes(qMarkerSecondPhase)||firstP9;
  const secondShift=['p7-shift-write','p7-shift-clear','p7-shift-read'].includes(qMarkerSecondPhase)||firstFrontier;
  const secondRead=qMarkerSecondPhase==='p7-shift-read'||firstFrontier;
  const secondErase=secondRead||qMarkerSecondPhase==='p7-shift-clear';
  const packetSecondActions=qMarkerSecondPhase===null?[]:[
    ['packet-second-backup-first',['X→П','9'],0x49],
    ...packetRepeatTemplate.slice(0,15).map(([label,keys,code])=>['packet-second-'+label,keys,code]),
    ['packet-second-probe-zero',['П→X','0'],0x60],
    ...(qMarkerSecondPhase==='p9-source-write'||secondShift?[
      ['packet-second-source-clear',['Сx'],0x0D],
      ...Array.from('24681357',(key,i)=>['packet-second-source'+(i+1),[key],Number(key)]),
      ['packet-second-source-store',['X→П','7'],0x47],
      ['packet-second-source-after-clear',['Сx'],0x0D],
      ...Array.from({length:4},(_,i)=>['packet-second-source-flush'+(i+1),['П→X','0'],0x60])]:[]),
    ...(['p9-write','p9-source-write'].includes(qMarkerSecondPhase)||secondShift?[
      ['packet-second-open1',['П→X','ВП'],0x6C],['packet-second-open2',['П→X','Сx'],0x6D],
      ['packet-second-open3',['П→X','8'],0x68],['packet-second-open4',['П→X','7'],0x67],
      ...(secondShift?[
        // Derived from the actual E7/A8 frame, not a keyboard sweep:
        // U->V->W->Q through three U..Q pushes; Q..P9 then copies Q toP7.
        // The public suffix is fixed before running either fresh reference.
        ...Array.from({length:3},(_,i)=>['packet-second-shift'+(i+1),['П→X','8'],0x68]),
        ['packet-second-shift-Q',['П→X','Сx'],0x6D],
        ...(secondErase?[
          // STORE reads the actual zero in Q; no Cx in mixed geometry.
          ['packet-second-erase6',['X→П','6'],0x46],
          ['packet-second-erase7',['X→П','7'],0x47]]:[]),
        ...(secondRead?[
          ['packet-second-read-open',['П→X','7'],0x67],
          ['packet-second-read-output',['X→П','6'],0x46]]:[]),
        ...(firstP9?[
          // Calculated original keyboard prefix: first make P9/FFF by a
          // harmless rejecting call, then its actual9C entry uses P8 base.
          ['packet-second-first-adapter',['П→X','4'],0x64],
          ['packet-second-first-V',['П→X',','],0x6A],
          ['packet-second-first-W',['П→X',','],0x6A],
          ['packet-second-first-Y',['П→X','6'],0x66],
          ...(qMarkerSecondPhase==='p7-first-read'||secondNormal?[
            ['packet-second-first-T',['П→X','7'],0x67],
            ['packet-second-first-X1',['П→X','7'],0x67],
            ['packet-second-first-Wzero',['Сx'],0x0D],
            ['packet-second-first-X1zero',['П→X','4'],0x64],
            ...Array.from({length:4},(_,i)=>['packet-second-first-flush'+(i+1),['П→X','5'],0x65]),
            ['packet-second-first-read',['F','В↑'],0x0F],
            ['packet-second-first-output',['X→П',','],0x4A]]:[])]:firstFrontier?[
          ['packet-second-first1',['П→X','4'],0x64],
          ['packet-second-first2',['П→X','4'],0x64],
          ['packet-second-first3',['П→X','/-/'],0x6B]]:[])]:[
      ['packet-second-open5',['П→X','ВП'],0x6C],
      ...(qMarkerSecondPhase==='p9-write'?[['packet-second-input-clear',['Сx'],0x0D],
        ...Array.from('24681357',(key,i)=>['packet-second-input'+(i+1),[key],Number(key)])]:[]),
      ['packet-second-write',['K','5'],0x32]])]:[])];
  const secondNormalActions=secondNormal?[
    ['packet-normal-clear',['Сx'],0x0D],['packet-normal-erase6',['X→П','9'],0x49],
    ['packet-normal-erase7',['X→П',','],0x4A],
    ['packet-normal-aux0',['П→X','6'],0x66],['packet-normal-port5',['X→П','8'],0x48],
    ['packet-normal-Y',['П→X','8'],0x68],['packet-normal-X1',['П→X','/-/'],0x6B],
    ...(secondRetain?[
      ...Array.from({length:3},(_,i)=>['packet-normal-retain-shift'+(i+1),['П→X',','],0x6A]),
      ['packet-normal-retain-clearP8',['Сx'],0x0D],
      ['packet-normal-retain-header',['П→X','8'],0x68],
      ['packet-normal-retain-X1',['П→X','5'],0x65],
      ...Array.from({length:4},(_,i)=>['packet-normal-retain-flush'+(i+1),['П→X','4'],0x64]),
      ['packet-normal-port5-zero',['X→П','5'],0x45]]:[
    ['packet-normal-relocate',['П→X','В↑'],0x6E],
    ['packet-normal-adapter',['П→X','4'],0x64],
    ...Array.from({length:4},(_,i)=>['packet-normal-flush'+(i+1),['П→X','4'],0x64]),
    ['packet-normal-port5-zero',['X→П','5'],0x45]]),
    ...(['p8-normal-math','p8-reopen-control','p8-reopen-clear','p8-reopen-swap','p7-normal-retain-math','p7-normal-retain-read','p7-normal-retain-both'].includes(qMarkerSecondPhase)||secondProgram||p7Repeat||p7Write3?[
      ['packet-normal-math-clear',['Сx'],0x0D],['packet-normal-two',['2'],0x02],
      ['packet-normal-enter',['В↑'],0x0E],['packet-normal-three',['3'],0x03],
      ['packet-normal-plus',['+'],0x10],['packet-normal-lastx',['F','В↑'],0x0F],
      ['packet-normal-after-clear',['Сx'],0x0D],
      ...Array.from({length:4},(_,i)=>['packet-normal-preclear'+(i+1),['П→X','0'],0x60])]:[]),
    ...(['p7-normal-retain-read','p7-normal-retain-both'].includes(qMarkerSecondPhase)||p7Repeat||p7Write3?[
      ...Array.from({length:4},(_,i)=>['packet-p7-read-F'+(i+1),['П→X','3'],0x63]),
      ['packet-p7-read-U',['П→X','7'],0x67],['packet-p7-read-V',['П→X','7'],0x67],
      ['packet-p7-read-clearY',['Сx'],0x0D],
      ...Array.from({length:3},(_,i)=>['packet-p7-read-front'+(i+1),['П→X','4'],0x64]),
      ['packet-p7-read-output',['X→П','6'],0x46]]:[]),
    ...(qMarkerSecondPhase==='p7-normal-retain-both'||p7Repeat||p7Write3?[
      ...Array.from({length:3},(_,i)=>['packet-p7-first-Y'+(i+1),['П→X','3'],0x63]),
      ['packet-p7-first-P8',['П→X',','],0x6A],
      ['packet-p7-first-Wzero1',['П→X',','],0x6A],['packet-p7-first-Wzero2',['П→X',','],0x6A],
      ['packet-p7-first-aux0',['П→X','6'],0x66],
      ['packet-p7-first-T',['П→X','7'],0x67],['packet-p7-first-X1',['П→X','7'],0x67],
      ['packet-p7-first-Wzero',['Сx'],0x0D],['packet-p7-first-X1zero',['П→X','4'],0x64],
      ...Array.from({length:4},(_,i)=>['packet-p7-first-flush'+(i+1),['П→X','5'],0x65]),
      ['packet-p7-first-read',['F','В↑'],0x0F],['packet-p7-first-output',['X→П',','],0x4A]]:[]),
    ...(secondProgram?[
      ['packet-program-edit-home',['В/О'],0x52],['packet-program-edit',['F','ВП'],null],
      ['packet-program-edit-swap',['↔'],0x14],['packet-program-edit-stop',['С/П'],0x50],
      ['packet-program-auto',['F','/-/'],null]]:[]),
    ...(['p8-reopen-control','p8-reopen-clear','p8-reopen-swap'].includes(qMarkerSecondPhase)||secondProgram?[
      ...Array.from({length:4},(_,i)=>['packet-reopen-control-F'+(i+1),['П→X','3'],0x63]),
      ['packet-reopen-control-U',['П→X','7'],0x67],
      ['packet-reopen-control-V',['П→X','7'],0x67],
      ...(['p8-reopen-clear','p8-reopen-swap'].includes(qMarkerSecondPhase)||secondProgram?[
        ['packet-reopen-control-clearY',['Сx'],0x0D]]:[]),
      ...(qMarkerSecondPhase==='p8-reopen-swap'||secondProgram?[
        ...Array.from({length:3},(_,i)=>['packet-reopen-control-front'+(i+1),['П→X','4'],0x64]),
        ...(secondProgram?[
          ['packet-program-run-home',['В/О'],0x52],['packet-program-run',['С/П'],0x50],
          ['packet-program-output',['X→П','6'],0x46]]:[
          ['packet-reopen-control-swap',['↔'],0x14]])]:[
        ['packet-reopen-control-unsafe',['П→X',','],0x6A]])]:[])]:[];
  const secondRetainRepeatActions=p7Repeat?[
    ['packet-p7-repeat-inlet',[],null],
    ...secondNormalActions.map(([label,keys,code])=>['packet-p7-repeat-'+label.slice(7),keys,code]),
    ['packet-p7-repeat-idle',[],null]]:[];
  const thirdActions=p7Write3?[
    ...secondNormalActions.slice(0,secondNormalActions.findIndex(v=>v[0]==='packet-normal-port5-zero')+1)
      .filter(v=>!['packet-normal-erase6','packet-normal-erase7'].includes(v[0]))
      .map(([label,keys,code])=>['packet-third-normal-'+label.slice(14),keys,code]),
    ['packet-third-source-clear',['Сx'],0x0D],
    ...Array.from('1.3579246E-50',(ch,i)=>['packet-third-source'+i,
      [ch==='.'?',':ch==='E'?'ВП':ch==='-'?'/-/':ch],ch==='.'?0x0A:ch==='E'?0x0C:ch==='-'?0x0B:Number(ch)]),
    ['packet-third-source-R4',['X→П','4'],0x44],['packet-third-source-R8',['X→П','8'],0x48],
    ['packet-third-after-clear',['Сx'],0x0D],
    ...Array.from({length:4},(_,i)=>['packet-third-after-flush'+i,['П→X','0'],0x60]),
    ...Array.from({length:4},(_,i)=>['packet-third-V-F'+i,['П→X','3'],0x63]),
    ['packet-third-V-U',['П→X','7'],0x67],['packet-third-V-V',['П→X','7'],0x67],
    ['packet-third-V-clearY',['Сx'],0x0D],
    ...Array.from({length:3},(_,i)=>['packet-third-V-front'+i,['П→X','5'],0x65]),
    ['packet-third-write-Z1',['П→X','3'],0x63],['packet-third-write-Z2',['П→X','3'],0x63],
    ['packet-third-write-W',['П→X',','],0x6A],['packet-third-write-Y',['П→X','7'],0x67],
    ['packet-third-write-Q',['П→X','Сx'],0x6D],
    ['packet-third-write-clear1',['П→X','8'],0x68],
    ['packet-third-write-clear2',['П→X','0'],0x60],
    ['packet-third-write-clear3',['П→X','В↑'],0x6E],
    ['packet-third-write-clear4',['П→X',','],0x6A],
    ['packet-third-write-Y2',['П→X','9'],0x69],
    ['packet-third-write-P9',['П→X','Сx'],0x6D],
    ...(p7Restore3?[
      ['packet-third-restore-dropAux1',['F','В↑'],0x0F],
      ['packet-third-restore-FIRST',['П→X','ВП'],0x6C],
      ...(p7Restore3CX?[['packet-third-restore-CX',['Сx'],0x0D]]:[])]:[])]:[];
  for(const [label,,code] of [...packetSecondActions,...secondNormalActions,...secondRetainRepeatActions,...thirdActions])
    if(label!=='packet-program-run')packetCodes[label]=code;
  assert.ok([1,2,3].includes(qMarkerRepeatCount),'bounded repeats of the SAME source-directed protocol, not a keyboard sweep');
  const packetIdle=label=>label==='packet-idle'||/^packet-repeat\d*-idle$/.test(label)||/^packet-p7-repeat-(inlet|idle)$/.test(label);
  const packetRepeatActions=Array.from({length:qMarkerRepeatCount},(_,i)=>{
    const prefix='packet-repeat'+(i?i+1:'')+'-';
    return [...packetRepeatTemplate.map(([label,keys,code])=>[prefix+label,keys,code]),
      ...(i+1<qMarkerRepeatCount?[[prefix+'idle',[],null]]:[])];
  }).flat();
  if(qMarkerRepeat)for(const [label,,code] of packetRepeatActions)if(code!==null)packetCodes[label]=code;
  assert.ok(!qMarkerRepeat||qMarkerPacket==='yku','one fixed repeat from proved post-normal-work P10 read');
  assert.ok(!qMarkerRepeatClear||qMarkerRepeat,'canonical stack zero flush only in the fixed repeat protocol');
  assert.ok(qMarkerPacket===null||packetRank>0,
    'one source-selected earlier marker-packet preparation, no keyboard sweep');
  assert.ok(qMarkerPacket===null||(qRestoreControl==='noP9'&&qRestoreIdleCheck
    &&!qControllerZeroAfterCx&&!qRestoreCalcCheck&&qTRecoveryProfile===null),
    'packet preparation forks before old Q/P9/T cleanup, with native initial F reserve');
  assert.ok(['1.0000003','1.2345678'].includes(ghostMultiplier),
    'two source-derived arithmetic payload fixtures only');
  assert.ok(!qAddressIdleCheck||(qReserveGhost8&&qAddressRead==='D'),
    'payload stability control requires the native ghost8/READD route');
  assert.ok(qPayloadExit===null||['auto','program_auto','decode','raw_read','raw_read_control','exponent_read','plain_roundtrip'].includes(qPayloadExit),
    'source-selected mode, raw-readback and numerical-decoder controls only');
  assert.ok(qPayloadExit===null||qAddressIdleCheck,'exit starts after the native payload/idle proof');
  assert.ok(qPayloadExit!=='decode'||qInverseScale,'decoder requires the native inverse-scale reserve');
  assert.ok(qPayloadExit!=='plain_roundtrip'||qNormalReserve,
    'plain roundtrip requires a native normal P6 reservoir and the single-Q context');
  assert.ok(!qReadbackIdleCheck||['raw_read','raw_read_control','plain_roundtrip'].includes(qPayloadExit),
    'readback idle follows the source-derived positive/control program');
  const ghostWord=qPlainPayload?'007012345678':
    ghostMultiplier==='1.0000003'?'600010000003':'600012345678';
  hashes();const fresh=()=>{
    if(!minimal)return setup(false,'10');
    const {MK61}=require('/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs');
    const c=new MK61();assert.equal(c.extended,true);
    for(const n of ['setRegister','writeCommand','loadProgram','writeNumber'])
      c[n]=()=>{throw Error('Forbidden setter: '+n);};
    return aligned(c);
  };
  const c=fresh(),plain=fresh();
  if(qNormalReserve) {
    for(const x of [c,plain]) {
      x.inputNumber(normalInput.startsWith('-')?normalInput.slice(1):normalInput,{clear:true});
      if(normalInput.startsWith('-'))x.press('/-/');
      x.pressSequence(['X→П','6']);aligned(x);
    }
    assert.deepEqual(dump(c),dump(plain),'fresh observer-free ordinary12345678 reserve');
    assert.equal(rawRegister(c,6),normalWord);
  }
  let ghostPrepared=null;
  if(qReserveGhost8) {
    for(const x of [c,plain]) {
      if(qPlainPayload) {
        x.inputNumber('12345678',{clear:true}).pressSequence(['X→П','8']);aligned(x);
      }
      else if(qInverseScale)require('./cache-bc-head93-q-payload-roundtrip-native.cjs')
        .prepareInverseScale(x,ghostMultiplier);
      else {
        arithmetic(x,'1E75',ghostMultiplier,8);
        x.pressSequence(['В/О','С/П']).runFrames(12);aligned(x);
      }
      assert.equal(rawRegister(x,8),ghostWord,'arithmetic source is real ordinaryP8');
      x.inputNumber('0',{clear:true}).pressSequence(['X→П','0']);aligned(x);
      assert.equal(rawRegister(x,8),ghostWord);
      assert.equal(rawRegister(x,0),'000000000000');
    }
    assert.deepEqual(dump(c),dump(plain),'fresh observer-free arithmetic ghost8 reservoir');
    ghostPrepared=snapshot(c);
  }
  const install=['В/О','F','ВП','С/П','F','/-/','В/О'];
  for(const x of [c,plain])press(x,install);
  assert.equal(c.readCommand(0),0x50);assert.deepEqual(dump(c),dump(plain));
  const recipe=logical?['Сx','K','Сx','K','8']
    :['Сx',...Array(zeros).fill('0'),'/','ВП','K','0'];
  for(const x of [c,plain])press(x,recipe);
  assert.deepEqual(dump(c),dump(plain));const blank=snapshot(c);
  const original=c.tick.bind(c),events=[],windows={stop:[],store:[],...(readBack?{read:[]}: {})},nativeIdleStates={},nativeEndpoints={};
  const {tags,cells}=initialTags(c);let event=null,word=-1,stage='stop',record=null,active=false,
    runStopSeen=false;
  const calcAudit={checkedWords:0,stageCounts:{},numberHeld:true};
  const postCalcAudit={checkedWords:0,stageCounts:{},numberHeld:true,firstDifference:null};
  const tRecoveryAudit={checkedWords:0,stageCounts:{},numberHeld:true,firstDifference:null};
  const packetAudit={checkedWords:0,stageCounts:{},numberHeld:true,firstDifference:null};
  const secondSlotAudit=secondShift?
    {checkedWords:0,stageCounts:{},numberHeld:true,firstDifference:null,word:'007024681357',writes:[]}:null;
  let secondSlotWritten=false,secondSlotWriteThisWord=false;
  const secondRelocationAudit=secondNormal?{checkedWords:0,stageCounts:{},numberHeld:true,
    firstDifference:null,location:'P7',moves:[]}:null;
  let relocationToA=false,relocationToP8=false;
  const thirdAudit=p7Write3?{checkedWords:0,firstHeldInR7:true,secondHeldInP7:true,
    firstDifference:null,sourceReady:false,stored:false,thirdHeld:true,thirdFirstDifference:null,word:'950013579246',writes:[]}:null;
  let thirdWriteThisWord=false;
  const thirdRestoreAudit=p7Restore3?{checkedWords:0,holdersHeld:true,holderDifference:null,
    bankReady:false,bankHeld:true,bankDifference:null,bankStart:null,
    wanted:{P7:'007024681357',P9:normalWord,P10:'950013579246'},
    boundary:'three physical Ms payloads only; ordinary input/output reserves not erased, P9 header not canonical, no independent third read/work cycle'}:null;
  const auditThirdRestore=moment=>{
    if(!thirdRestoreAudit||(!stage.startsWith('packet-third-restore-')&&!(stage==='packet-idle'&&thirdRestoreAudit.bankReady)))return;
    if(moment==='before')thirdRestoreAudit.checkedWords++;
    for(const [holder,wanted] of [['R7',normalWord],['R6','007024681357'],['R4','950013579246']]){
      const actual=observedNumeric('register',holder);
      if(actual!==wanted){thirdRestoreAudit.holdersHeld=false;
        thirdRestoreAudit.holderDifference??={word,stage,moment,holder,actual};}
    }
    const bank=Object.fromEntries(['P7','P9','P10'].map(w=>[w,observedNumeric('Ms',w)]));
    const held=Object.entries(thirdRestoreAudit.wanted).every(([w,n])=>bank[w]===n);
    if(!thirdRestoreAudit.bankReady&&held){thirdRestoreAudit.bankReady=true;
      thirdRestoreAudit.bankStart={word,stage,moment,bank};}
    if(thirdRestoreAudit.bankReady&&!held){thirdRestoreAudit.bankHeld=false;
      thirdRestoreAudit.bankDifference??={word,stage,moment,bank};}
  };
  const bankFootprint=p7Repeat?{checkedWords:0,stages:{},pages:{},
    boundary:'potential ROM writes/reads at the actually observed all5 control paths; not global impossibility/arbitrary new-data reachability'}:null;
  const memoryMasks=p7Repeat?require('./cache-bc-head93-rom-memory-masks.cjs').masks:null;
  const auditRelocation=moment=>{
    const location=secondRelocationAudit.location;
    const actual=location==='A'?working(c.ik1302):observedNumeric('Ms',location);
    if(actual!=='007024681357'){secondRelocationAudit.numberHeld=false;
      secondRelocationAudit.firstDifference??={word,stage,moment,location,actual};}
  };
  const auditSecondSlot=moment=>{
    const actual=observedNumeric('Ms','P7');
    if(actual!==secondSlotAudit.word){secondSlotAudit.numberHeld=false;
      secondSlotAudit.firstDifference??={word,stage,moment,actual};}
  };
  const lateNumberAudit=qMarkerLateNumber===null?null:{checkedWords:0,stageCounts:{},contractHeld:true,
    firstDifference:null,oldWord:normalWord,newWord:lateWords[qMarkerLateNumber],writes:[]};
  let lateNumberWritten=false,lateWriteThisWord=false;
  const auditLateNumber=(actual,moment)=>{
    const expected=lateNumberWritten?lateWords[qMarkerLateNumber]:normalWord;
    if(actual!==expected){lateNumberAudit.contractHeld=false;
      lateNumberAudit.firstDifference??={word,stage,moment,expected,actual};}
  };
  let tRecoveryControlSeen=false;
  let packetControlSeen=false;
  const tRecoveryCodes={'t-recovery-sign':0x32,'t-recovery-zero1':0x60+parseInt(qTZeroDigit,16),
    't-recovery-enter1':0x0E,'t-recovery-lastx1':0x0F};
  const completed={stop:false,store:false,...(readBack?{read:false}: {})};
  const working=p=>p.r.filter((_,j)=>j%3===0).slice(0,12).reverse()
    .map(v=>v.toString(16).toUpperCase()).join('');
  const observedNumeric=(area,wordName)=>{
    const values=Array(12).fill(undefined);
    for(let chip=1;chip<=5;chip++)for(let j=0;j<tags[chip].length;j++) {
      const cell=cells[tags[chip][j]];
      if(cell.area===area&&cell.word===wordName&&Number.isInteger(cell.field))
        values[cell.field]=c[chips[chip]].memory[j];
    }
    assert.ok(values.every(v=>Number.isInteger(v)));
    return values.reverse().map(v=>v.toString(16).toUpperCase()).join('');
  };
  c.tick=function(){
    const p=this.ik1302,j=p.tickIndex;
    const indices=chips.map((n,i)=>i?this[n].tickIndex:0);
    if(j===0) {
      word++;const ip=p.r[36]+16*p.r[39];
      const owner=cells[tags[3][22]];
      relocationToA=secondNormal&&stage==='packet-normal-relocate'&&ip===0xA8&&owner.area==='Ms'&&owner.word==='P7';
      relocationToP8=secondNormal&&stage==='packet-normal-relocate'&&ip===0xA8&&owner.area==='Ms'&&owner.word==='P8';
      if(secondRelocationAudit&&secondSlotWritten) {
        secondRelocationAudit.checkedWords++;
        secondRelocationAudit.stageCounts[stage]=(secondRelocationAudit.stageCounts[stage]||0)+1;
        auditRelocation('before');
      }
      secondSlotWriteThisWord=secondSlotAudit!==null&&stage==='packet-second-shift-Q'&&ip===0xA8
        &&cells[tags[3][22]].area==='Ms'&&cells[tags[3][22]].word==='P7';
      if(secondSlotWriteThisWord) {
        assert.equal(working(p),secondSlotAudit.word,'PASSIVE Q displacement must contain the complete second number');
        assert.equal(secondSlotWritten,false,'one planned second-slot write');
      }
      if(secondSlotWritten) {
        secondSlotAudit.checkedWords++;
        secondSlotAudit.stageCounts[stage]=(secondSlotAudit.stageCounts[stage]||0)+1;
        auditSecondSlot('before');
      }
      lateWriteThisWord=qMarkerLateNumber!==null&&stage==='packet-late-sign'&&ip===0xE9;
      if(lateWriteThisWord){
        const owner=[...new Set(tags[3].filter((_,k)=>k%3===1).map(id=>cells[id].area+':'+cells[id].word))];
        assert.deepEqual(owner,['Ms:P10'],'planned lateE9 must really address physicalP10');
        assert.equal(working(p),lateWords[qMarkerLateNumber],'planned source is the entered new number');
      }
      if(qRestoreControl==='noP9'&&stage.startsWith('restore-test-')) {
        assert.equal(observedNumeric('Ms','P10'),normalWord,
          'PASSIVE native P10 before every diagnostic word; no action feedback');
        calcAudit.checkedWords++;
        calcAudit.stageCounts[stage]=(calcAudit.stageCounts[stage]||0)+1;
      }
      if(stage.startsWith('restore-post-')) {
        postCalcAudit.checkedWords++;
        postCalcAudit.stageCounts[stage]=(postCalcAudit.stageCounts[stage]||0)+1;
        const actual=observedNumeric('Ms','P10');
        if(actual!==normalWord) {
          postCalcAudit.numberHeld=false;
          postCalcAudit.firstDifference??={word,stage,moment:'before',actual};
        }
      }
      if(stage.startsWith('t-recovery-')) {
        tRecoveryAudit.checkedWords++;
        tRecoveryAudit.stageCounts[stage]=(tRecoveryAudit.stageCounts[stage]||0)+1;
        const actual=observedNumeric('Ms','P10');
        if(actual!==normalWord) {
          tRecoveryAudit.numberHeld=false;
          tRecoveryAudit.firstDifference??={word,stage,moment:'before',actual};
        }
      }
      if(stage.startsWith('packet-')) {
        packetAudit.checkedWords++;
        packetAudit.stageCounts[stage]=(packetAudit.stageCounts[stage]||0)+1;
        const actual=observedNumeric('Ms','P10');
        if(actual!==normalWord) {
          packetAudit.numberHeld=false;
          packetAudit.firstDifference??={word,stage,moment:'before',actual};
        }
        if(lateNumberAudit){lateNumberAudit.checkedWords++;
          lateNumberAudit.stageCounts[stage]=(lateNumberAudit.stageCounts[stage]||0)+1;
          auditLateNumber(actual,'before');}
      }
      const owners=offset=>[...new Set(tags[3].filter((_,j)=>j%3===offset)
        .map(id=>cells[id].area+':'+cells[id].word))];
      if(thirdAudit&&stage.startsWith('packet-third-')) {
        thirdAudit.checkedWords++;
        if(observedNumeric('register','R7')!==normalWord){thirdAudit.firstHeldInR7=false;
          thirdAudit.firstDifference??={word,stage,moment:'before',holder:'R7',actual:observedNumeric('register','R7')};}
        if(observedNumeric('Ms','P7')!=='007024681357'){thirdAudit.secondHeldInP7=false;
          thirdAudit.firstDifference??={word,stage,moment:'before',holder:'Ms:P7',actual:observedNumeric('Ms','P7')};}
        if(stage==='packet-third-V-F0'&&!thirdAudit.sourceReady) {
          assert.equal(observedNumeric('register','R4'),thirdAudit.word,'typed native third source R4');
          assert.equal(observedNumeric('register','R8'),thirdAudit.word,'typed native third source R8');
          thirdAudit.sourceReady=true;
        }
        if(stage==='packet-third-write-P9'&&ip===0xE7&&owners(1)[0]==='Ms:P9') {
          assert.equal(working(p),thirdAudit.word,'planned native P9 writer source');
          thirdWriteThisWord=true;
        }
      }
      if(thirdAudit?.stored&&observedNumeric('Ms','P9')!==thirdAudit.word) {
        thirdAudit.thirdHeld=false;
        thirdAudit.thirdFirstDifference??={word,stage,moment:'before',actual:observedNumeric('Ms','P9')};
      }
      auditThirdRestore('before');
      if(bankFootprint&&stage.startsWith('packet-p7-repeat-')&&stage!=='packet-p7-repeat-inlet') {
        bankFootprint.checkedWords++;
        bankFootprint.stages[stage]=(bankFootprint.stages[stage]||0)+1;
        for(const index of [3,4,5]) {
          const name=chips[index],part=this[name],code=part.r[36]+16*part.r[39];
          for(const kind of ['read','write'])for(const j of memoryMasks(name,code)[kind]) {
            const cell=cells[tags[index][j]];
            if(cell.area!=='Ms'||!Number.isInteger(cell.field))continue;
            const page=bankFootprint.pages[cell.word]??={readMask:0,writeMask:0,witness:{}};
            page[kind+'Mask']|=1<<cell.field;
            const key=kind+':'+cell.field;
            page.witness[key]??={word,stage,chip:name,ip:code,cell:j};
          }
        }
      }
      const cleanupCode=stage==='zero-r9-source'?0x49:
        stage==='restore-marker-store'?0x43:stage==='restore-marker-C-store'?0x4C:
        stage==='restore-readF1'?0x68:
        stage==='restore-readF2'?0x65:
        stage==='restore-lastx'?0x0F:
        stage==='restore-backup'?0x4E:
        stage==='restore-backupD'?0x43:stage==='restore-backupE'?0x44:
        stage==='restore-clear-ghost'?0x4D:
        stage==='restore-seed9'?0x4E:stage==='restore-wipeQ-zero8'?0x60+parseInt(qControllerZeroDigit,16):
        ['restore-U-marker','restore-U-marker-ack'].includes(stage)?0x6B:
        stage==='restore-P9-clear'?0x60+parseInt(qControllerAck?qControllerClearDigit:'E',16):
        stage==='restore-zero-after-cx'?0x60+parseInt(qControllerPostCxDigit,16):
        ['restore-visibleF1','restore-visibleF2'].includes(stage)?0x68:
        stage==='restore-eraseQ'?0x60:
        stage==='restore-plantZ'?0x68:stage==='restore-wipeQ'?0x60:
        stage==='restore-test-cx'?0x0D:stage==='restore-test-two'?0x02:
        stage==='restore-test-enter'?0x0E:stage==='restore-test-three'?0x03:
        stage==='restore-test-plus'?0x10:
        stage==='cleanup-cx'?0x0D:stage.startsWith('cleanup-r0-')?0x60:
        stage.startsWith('cleanup-r2-')?0x62:
        stage==='normal-use-one'?0x01:stage==='normal-use-plus'?0x10:
        stage==='q-address-read'?0x60+parseInt(qAddressRead,16):null;
      const cleanupAccepted=cleanupCode!==null&&ip===0x9C
        &&p.r[30]+16*p.r[33]===cleanupCode
        &&(p.memory[31]===15?p.memory[34]>=1:p.memory[34]>=7);
      const controllerPriming=qRestoreControl==='noP9'&&stage==='restore-U-marker';
      const primingAttempt=controllerPriming&&ip===0x9C
        &&p.r[30]+16*p.r[33]===cleanupCode;
      const tRecoveryCode=tRecoveryCodes[stage];
      const tRecoveryAttempt=tRecoveryCode!==undefined&&ip===0x9C
        &&p.r[30]+16*p.r[33]===tRecoveryCode;
      const packetCode=packetCodes[stage];
      const packetAttempt=packetCode!==undefined&&ip===0x9C&&p.r[30]+16*p.r[33]===packetCode;
      const secondProgramRun=secondProgram&&stage==='packet-program-run';
      const fullProgramRun=secondProgramRun||((stage==='payload-exit-run'||stage==='payload-readback-run')
        &&['decode','raw_read','raw_read_control','exponent_read','plain_roundtrip'].includes(qPayloadExit));
      if(fullProgramRun&&ip===0x9C&&p.r[30]+16*p.r[33]===0x50)runStopSeen=true;
      if(secondProgramRun&&!active)runStopSeen=false;
      if(proof&&windows[stage]&&!active&&!completed[stage]
        &&(fullProgramRun?(ip===0x9C&&p.r[30]+16*p.r[33]===
            (secondProgramRun?0x14:stage==='payload-readback-run'?(qPlainControl==='no_swap'?0x4E:0x14):
              qPayloadExit==='plain_roundtrip'?0x6B:0x4D)):
          (cleanupAccepted||primingAttempt||tRecoveryAttempt||packetAttempt||packetIdle(stage)||stage==='t-recovery-idle'||stage.startsWith('payload-exit-')||stage.startsWith('restore-test-')||stage.startsWith('restore-post-')||['q-idle','cleanup-idle','q-address-idle','q-readback-idle','plain-storage-idle','restore-idle','restore-next-idle'].includes(stage)||
          (cleanupCode===null&&ip===(stage.startsWith('marker-read')?0x01:
          stage.startsWith('read')?(traceSeek?0x01:0xD6):stage==='lastx-lift'?0xEE:
          ['digit-lift','clear-real','q-lastx'].includes(stage)?0xE7:0x9F)))))active=true;
      if(active) {
        record={word,ip,fullBefore:fullState(this),tagsBefore:fullTags(tags),
          keysX:[],keysY:[],emitted:[],ordinaryOwner:owners(0),numericOwner:owners(1)};
        windows[stage].push(record);
      }
      event=[0x9C,0x9D,0x9E,0x9F,0xAA,0xEE,0xE7,0xE9,0xA1,0xA2,0xD4,0xD6,0xA7,0xE8,0xA8,0x01,0x02,
        0xDE,0xA3,0xBB,0xBC,0xBE,0x34].includes(ip)
        ?{word,ip,R41:p.r[41],A:working(p),read:p.memory.filter((_,k)=>k%3===1)
          .slice(0,12).reverse().map(v=>v.toString(16).toUpperCase()).join(''),
          readM1:p.memory.filter((_,k)=>k%3===0).slice(0,12).reverse()
            .map(v=>v.toString(16).toUpperCase()).join(''),stage,
          ordinaryOwner:owners(0),numericOwner:owners(1),R29:p.r[29],R32:p.r[32],R35:p.r[35],
          B:p.r.filter((_,k)=>k%3===1).slice(0,12).reverse()
            .map(v=>v.toString(16).toUpperCase()).join(''),
          opcode:p.r[30]+16*p.r[33],modeR2:p.r[2],
          returnTop:p.stack[36]+16*p.stack[39],guardM:[p.memory[31],p.memory[34]]}:null;
      if(event)events.push(event);
    }
    const observe=active,old=indices.map((j,i)=>i?tags[i][j]:0);
    if(observe){record.keysX.push(p.keyX);record.keysY.push(p.keyY);}
    const result=original();
    const incoming=[0,old[5],old[1],old[2],old[3],old[4]];
    for(let i=1;i<=5;i++)tags[i][indices[i]]=incoming[i];
    if(p.tickIndex===0&&secondSlotWriteThisWord) {
      secondSlotWritten=true;
      secondSlotAudit.writes.push({word,stage,ip:0xA8,target:'Ms:P7',actual:observedNumeric('Ms','P7')});
    }
    if(p.tickIndex===0&&secondSlotWritten)auditSecondSlot('after');
    if(p.tickIndex===0&&secondRelocationAudit&&secondSlotWritten) {
      if(relocationToA){assert.equal(secondRelocationAudit.location,'P7');
        secondRelocationAudit.location='A';secondRelocationAudit.moves.push({word,stage,from:'P7',to:'A'});}
      if(relocationToP8){assert.equal(secondRelocationAudit.location,'A');
        secondRelocationAudit.location='P8';secondRelocationAudit.moves.push({word,stage,from:'A',to:'P8'});}
      auditRelocation('after');
    }
    if(p.tickIndex===0&&qRestoreControl==='noP9'&&stage.startsWith('restore-test-'))
      assert.equal(observedNumeric('Ms','P10'),normalWord,
        'PASSIVE native P10 after every diagnostic word; no action feedback');
    if(p.tickIndex===0&&thirdAudit&&stage.startsWith('packet-third-')) {
      if(thirdWriteThisWord){thirdWriteThisWord=false;thirdAudit.stored=true;
        thirdAudit.writes.push({word,stage,target:'Ms:P9',actual:observedNumeric('Ms','P9')});}
      if(observedNumeric('register','R7')!==normalWord){thirdAudit.firstHeldInR7=false;
        thirdAudit.firstDifference??={word,stage,moment:'after',holder:'R7',actual:observedNumeric('register','R7')};}
      if(observedNumeric('Ms','P7')!=='007024681357'){thirdAudit.secondHeldInP7=false;
        thirdAudit.firstDifference??={word,stage,moment:'after',holder:'Ms:P7',actual:observedNumeric('Ms','P7')};}
    }
    if(p.tickIndex===0&&thirdAudit?.stored&&observedNumeric('Ms','P9')!==thirdAudit.word) {
      thirdAudit.thirdHeld=false;
      thirdAudit.thirdFirstDifference??={word,stage,moment:'after',actual:observedNumeric('Ms','P9')};
    }
    if(p.tickIndex===0)auditThirdRestore('after');
    if(p.tickIndex===0&&stage.startsWith('restore-post-')) {
      const actual=observedNumeric('Ms','P10');
      if(actual!==normalWord) {
        postCalcAudit.numberHeld=false;
        postCalcAudit.firstDifference??={word,stage,moment:'after',actual};
      }
    }
    if(p.tickIndex===0&&stage.startsWith('t-recovery-')) {
      const actual=observedNumeric('Ms','P10');
      if(actual!==normalWord) {
        tRecoveryAudit.numberHeld=false;
        tRecoveryAudit.firstDifference??={word,stage,moment:'after',actual};
      }
    }
    if(p.tickIndex===0&&stage.startsWith('packet-')) {
      const actual=observedNumeric('Ms','P10');
      if(lateWriteThisWord){lateNumberWritten=true;
        lateNumberAudit.writes.push({word,stage,ip:0xE9,target:'Ms:P10',actual});}
      if(lateNumberAudit)auditLateNumber(actual,'after');
      if(actual!==normalWord) {
        packetAudit.numberHeld=false;
        packetAudit.firstDifference??={word,stage,moment:'after',actual};
      }
    }
    if(event&&p.tickIndex===0){event.afterR41=p.r[41];event.afterA=working(p);
      event.afterIp=p.r[36]+16*p.r[39];}
    if(observe) {
      record.emitted.push(p.output);
      if(p.tickIndex===0) {
        record.fullAfter=fullState(this);record.tagsAfter=fullTags(tags);
        const fullProgramRun=(secondProgram&&stage==='packet-program-run')||((stage==='payload-exit-run'||stage==='payload-readback-run')
          &&['decode','raw_read','raw_read_control','exponent_read','plain_roundtrip'].includes(qPayloadExit));
        const cxDamage=stage==='restore-test-cx'
          &&observedNumeric('Ms','P10')!=='007012345678';
        const controllerCxError=qRestoreControl==='noP9'&&stage==='restore-test-cx'
          &&record.ip===0xA3&&observedNumeric('Ms','V')==='FFF000000000';
        const primingDone=qRestoreControl==='noP9'&&stage==='restore-U-marker'
          &&record.ip===0xA3&&observedNumeric('stack','T')==='FFF000000000';
        const tRecoveryCall=['t-recovery-sign','t-recovery-zero1','t-recovery-enter1','t-recovery-lastx1'].includes(stage);
        if(tRecoveryCall&&record.ip===0xA3)tRecoveryControlSeen=true;
        const packetCall=Object.hasOwn(packetCodes,stage);
        if(packetCall&&record.ip===0xA3)packetControlSeen=true;
        if(packetIdle(stage)?windows[stage].length===30:
          packetCall?(record.ip===0xBE||(packetControlSeen&&record.ip===0x35&&p.r[2]===0&&p.keyX===0)):
          stage==='t-recovery-idle'?windows[stage].length===30:
          tRecoveryCall?(record.ip===0xBE||(tRecoveryControlSeen
            &&record.ip===0x35&&p.r[2]===0&&p.keyX===0)):
          stage.startsWith('restore-post-')?windows[stage].length===560:
          qRestoreControl==='noP9'&&stage==='restore-test-cx'?controllerCxError:
          stage.startsWith('restore-test-')?(stage==='restore-test-cx'?cxDamage:windows[stage].length===560):
          qRestoreControl==='noP9'&&stage==='restore-U-marker'?primingDone:
          fullProgramRun?(runStopSeen&&record.ip===0x35&&p.keyX===0
            &&(p.r[2]===8||(['exponent_read','plain_roundtrip'].includes(qPayloadExit)&&p.r[2]===15))):
          (stage.startsWith('payload-exit-')||['q-idle','cleanup-idle','q-address-idle','q-readback-idle','plain-storage-idle','restore-idle','restore-next-idle'].includes(stage))?windows[stage].length===30:
          (stage.startsWith('cleanup-')||stage.startsWith('normal-use-')||stage.startsWith('restore-')||['zero-r9-source','q-address-read'].includes(stage))?record.ip===0xBE:
          stage.startsWith('marker-read')&&qWholeTail?record.ip===0xBE:
          (stage.startsWith('marker-read')||['digit-lift','lastx-lift','clear-real','q-lastx'].includes(stage))
          ?[0xE7,0xA8].includes(record.ip)
          &&(p.r[36]+16*p.r[39]!==0xA8):record.ip===0xE7) {
          active=false;completed[stage]=true;
        }
        if(fullProgramRun)assert.ok(windows[stage].length<10000,'bounded selected program-run window');
        if(stage==='restore-test-cx')assert.ok(windows[stage].length<=8400,
          'bounded PASSIVE first-damage window; actions do not depend on observations');
      }
    }
    return result;
  };
  for(const x of [c,plain])press(x,['С/П']);
  assert.deepEqual(dump(c),dump(plain));const stopped=snapshot(c);
  stage='store';
  for(const x of [c,plain])press(x,['X→П','9']);
  assert.deepEqual(dump(c),dump(plain));const after=snapshot(c);
  const expected=logical?'9990FFFFFFF0':zeros===2?'0010F0000000':'0000F0000000';
  assert.equal(blank.words.Y,expected);
  assert.equal(after.R9,expected,'real STOP/EE/D4 rawF word reaches ordinaryR9');
  let markerPrepared=null;
  if(qRestoreControl!==null) {
    stage='restore-marker-store';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain])press(x,['X→П','3']);
    assert.deepEqual(dump(c),dump(plain),'fresh observer-free rawF ordinaryP3 reserve');
    markerPrepared=snapshot(c);assert.equal(markerPrepared.registers[3],expected);
    assert.equal(markerPrepared.R9,expected);
  }
  let extraMarkerPrepared=null;
  if(qMarkerPacket!==null) {
    stage='restore-marker-C-store';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain])press(x,['X→П','ВП']);
    assert.deepEqual(dump(c),dump(plain),'fresh observer-free extra rawF/C reserve');
    extraMarkerPrepared=snapshot(c);assert.equal(extraMarkerPrepared.registers[12],expected);
  }
  let read=null,cleared=null,reread=null,liftPrepared=null,lifted=null,lastX=null,
    realRemoved=null,zeroSource=null,qLifted=null,qStable=null,isolatedStable=null,addressed=null,addressStable=null;
  if(readBack) {
    stage='read';
    for(const x of [c,plain])press(x,['П→X',headerAdjustedRecall?'6':'9']);
    assert.deepEqual(dump(c),dump(plain));read=snapshot(c);
    assert.equal(read.R9,expected,'ordinary recall leaves source register intact');
    assert.deepEqual(read.program,after.program,'ordinary recall leaves program intact');
  }
  if(readAgainAfterClear) {
    stage='clear';
    for(const x of [c,plain])press(x,['Сx']);
    assert.deepEqual(dump(c),dump(plain));cleared=snapshot(c);
    stage='read-after-clear';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain])press(x,['П→X',headerAdjustedRecall?'6':'9']);
    assert.deepEqual(dump(c),dump(plain));reread=snapshot(c);
    assert.equal(reread.R9,expected);
    assert.deepEqual(reread.program,after.program);
  }
  if(clearDigitLift) {
    stage='clear-lift';
    for(const x of [c,plain])press(x,['Сx']);
    assert.deepEqual(dump(c),dump(plain));liftPrepared=snapshot(c);
    stage='digit-lift';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain])press(x,['0']);
    assert.deepEqual(dump(c),dump(plain));lifted=snapshot(c);
  }
  if(lastXLift) {
    stage='lastx-lift';
    if(!clearDigitLift){windows[stage]=[];completed[stage]=false;}
    for(const x of [c,plain])press(x,['F','В↑']);
    assert.deepEqual(dump(c),dump(plain));lastX=snapshot(c);
  }
  if(removeRealThenLastX) {
    stage='clear-real';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain])press(x,['П→X','0']);
    assert.deepEqual(dump(c),dump(plain));realRemoved=snapshot(c);
    if(qZeroSource) {
      stage='zero-r9-source';windows[stage]=[];completed[stage]=false;
      for(const x of [c,plain])press(x,['X→П','9']);
      assert.deepEqual(dump(c),dump(plain));zeroSource=snapshot(c);
    }
    stage=qReadInsteadLastX?'marker-read'+qReadDigit:'q-lastx';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain])press(x,qReadInsteadLastX?['П→X',qReadDigit]:['F','В↑']);
    assert.deepEqual(dump(c),dump(plain));qLifted=snapshot(c);
  }
  if(qIdleCheck) {
    stage='q-idle';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain]){x.runFrames(12);aligned(x);}
    assert.deepEqual(dump(c),dump(plain));qStable=snapshot(c);
    assert.deepEqual(qStable.words,qLifted.words,'complete numeric ring held during released-key idle');
    assert.deepEqual(qStable.registers,qLifted.registers);
    assert.deepEqual(qStable.program,qLifted.program);
  }
  const cleanupStages=[];
  if(qCleanup!==null) {
    const digit=qCleanup==='read2_twice'?'2':'0';
    const actions=[...(['read0_twice','read2_twice'].includes(qCleanup)?[]:[['cleanup-cx',['Сx']]]),
      ...(qCleanup!=='clear_v'
        ?[['cleanup-r'+digit+'-1',['П→X',digit]],['cleanup-r'+digit+'-2',['П→X',digit]]]:[])];
    for(const [label,keys] of actions) {
      stage=label;windows[stage]=[];completed[stage]=false;
      for(const x of [c,plain])press(x,keys);
      assert.deepEqual(dump(c),dump(plain),'fresh observer-free ALL5 '+label);
      cleanupStages.push({name:label,keys,...snapshot(c)});
    }
  }
  if(qFinalIdleCheck) {
    stage='cleanup-idle';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain]){x.runFrames(12);aligned(x);}
    assert.deepEqual(dump(c),dump(plain));isolatedStable=snapshot(c);
    assert.deepEqual(isolatedStable.words,cleanupStages.at(-1).words);
    assert.deepEqual(isolatedStable.registers,cleanupStages.at(-1).registers);
    assert.deepEqual(isolatedStable.program,cleanupStages.at(-1).program);
  }
  if(qAddressRead!==null) {
    stage='q-address-read';windows[stage]=[];completed[stage]=false;
    const registerKey=qAddressRead==='E'?'В↑':qAddressRead==='D'?'Сx':'9';
    for(const x of [c,plain])press(x,['П→X',registerKey]);
    assert.deepEqual(dump(c),dump(plain),'fresh observer-free ALL5 relative-address read');
    addressed=snapshot(c);
  }
  if(qAddressIdleCheck) {
    stage='q-address-idle';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain]){x.runFrames(12);aligned(x);}
    assert.deepEqual(dump(c),dump(plain),'fresh observer-free full payload idle');
    addressStable=snapshot(c);
    assert.deepEqual(addressStable.words,addressed.words);
    assert.deepEqual(addressStable.registers,addressed.registers);
    assert.deepEqual(addressStable.program,addressed.program);
  }
  const exitStages=[];
  const exitActions=qPayloadExit==='auto'?[['payload-exit-F',['F']],['payload-exit-auto',['/-/']]]:
    qPayloadExit==='program_auto'?[['payload-exit-F',['F']],['payload-exit-prog',['ВП']],
      ['payload-exit-K',['K']],['payload-exit-nop',['0']],['payload-exit-F2',['F']],
      ['payload-exit-auto',['/-/']]]:
    qPayloadExit==='decode'?[['payload-exit-F',['F']],['payload-exit-prog',['ВП']],
      ['payload-exit-source-zero',['X→П','Сx']],['payload-exit-swap',['↔']],
      ['payload-exit-inverse',['П→X','/-/']],['payload-exit-mul1',['*']],
      ['payload-exit-scale',['П→X',',']],['payload-exit-mul2',['*']],
      ['payload-exit-stop',['С/П']],['payload-exit-F2',['F']],
      ['payload-exit-auto',['/-/']],['payload-exit-jump',['БП','0','1']],
      ['payload-exit-run',['С/П']]]:
    ['raw_read','raw_read_control'].includes(qPayloadExit)?[
      ['payload-exit-F',['F']],['payload-exit-prog',['ВП']],
      ['payload-exit-source-zero',['X→П','Сx']],
      ...(qPayloadExit==='raw_read'?[['payload-exit-swap',['↔']]]:[]),
      ['payload-exit-store-readback',['X→П','В↑']],['payload-exit-stop',['С/П']],
      ['payload-exit-F2',['F']],['payload-exit-auto',['/-/']],
      ['payload-exit-jump',['БП','0','1']],['payload-exit-run',['С/П']]]:
    qPayloadExit==='exponent_read'?[
      ['payload-exit-F',['F']],['payload-exit-prog',['ВП']],
      ['payload-exit-source-zero',['X→П','Сx']],['payload-exit-swap',['↔']],
      ['payload-exit-exp',['ВП']],['payload-exit-seven',['7']],
      ['payload-exit-store-readback',['X→П','В↑']],['payload-exit-stop',['С/П']],
      ['payload-exit-F2',['F']],['payload-exit-auto',['/-/']],
      ['payload-exit-jump',['БП','0','1']],['payload-exit-run',['С/П']]]:
    qPayloadExit==='plain_roundtrip'?[
      ['payload-exit-F',['F']],['payload-exit-prog',['ВП']],
      ['payload-exit-read-normal',['П→X','/-/']],
      ...(qPlainControl==='no_enter'?[]:[['payload-exit-enter',['В↑']]]),
      ['payload-exit-clear',['Сx']],['payload-exit-clear-source',['X→П','/-/']],
      ['payload-exit-storage-stop',['С/П']],
      ...(qPlainControl==='no_swap'?[]:[['payload-exit-swap',['↔']]]),
      ['payload-exit-store-readback',['X→П','В↑']],
      ['payload-exit-stop',['С/П']],['payload-exit-F2',['F']],['payload-exit-auto',['/-/']],
      ['payload-exit-jump',['БП','0','1']],['payload-exit-run',['С/П']],
      ['plain-storage-idle',[]],
      ...(qRestoreControl===null?[['payload-readback-run',['С/П']]]:[]),
      ...(['readF','readF2','lastX','eraseQ','plantZ','wipeQ','wipeQShort','noZ','noP9'].includes(qRestoreControl)?[['restore-readF1',['П→X','8']]]:[]),
      ...(['readF2','lastX','eraseQ','plantZ','wipeQ','wipeQShort','noZ','noP9'].includes(qRestoreControl)?[['restore-readF2',['П→X','5']]]:[]),
      ...(['lastX','eraseQ','plantZ','wipeQ','wipeQShort','noZ','noP9'].includes(qRestoreControl)?[['restore-lastx',['F','В↑']]]:[]),
      ...(['eraseQ','plantZ','wipeQ','wipeQShort','noZ','noP9'].includes(qRestoreControl)?[
        qRestoreControl==='noP9'?(qMarkerPacket!==null?['restore-backupE',['X→П','4']]:
          ['restore-backupD',['X→П','3']]):['restore-backup',['X→П','В↑']],
        ...(['wipeQShort','noZ','noP9'].includes(qRestoreControl)?[]:[
          ['restore-visibleF1',['П→X','8']],['restore-visibleF2',['П→X','8']]]),
        ['restore-eraseQ',['П→X','0']]]:[]),
      ...(qRestoreControl==='noP9'?[['restore-clear-ghost',['X→П','Сx']]]:[]),
      ...(['plantZ','wipeQ','wipeQShort','noP9'].includes(qRestoreControl)?[['restore-plantZ',['П→X','8']]]:[]),
      ...(['wipeQ','wipeQShort','noZ'].includes(qRestoreControl)?[['restore-wipeQ',['П→X','0']]]:[]),
      ...(qRestoreControl==='noP9'&&qMarkerPacket===null?[
        ['restore-seed9',['X→П','В↑']],['restore-wipeQ-zero8',['П→X',qControllerZeroDigit==='A'?',':'Сx']],
        ['restore-U-marker',['П→X','/-/']],
        ...(qControllerAck?[['restore-U-marker-ack',['П→X','/-/']]]:[]),
        ['restore-P9-clear',['П→X',qControllerAck&&qControllerClearDigit==='5'?'5':'В↑']]]:[]),
      ...(qMarkerPacket!==null?[
        ['packet-seed8',['X→П','Сx']],['packet-plant-u',['П→X',',']],
        ...(packetRank>=2?[['packet-insert-q',['П→X','5']]]:[]),
        ...(packetRank>=3?[['packet-insert-q-ack',['П→X','5']]]:[]),
        ...(packetRank>=4?[['packet-move-q1',['П→X','3']]]:[]),
        ...(packetRank>=5?[['packet-move-q1-ack',['П→X',',']]]:[]),
        ...(qMarkerPacket==='m2'?[['packet-move-q2',['П→X','2']]]:[]),
        ...(packetRank>=6&&qMarkerPacket!=='m2'?[['packet-move-q2-A',['П→X',',']]]:[]),
        ...(packetRank>=7?[['packet-open-y',['П→X','В↑']]]:[]),
        ...(packetRank>=8&&qMarkerPacket!=='yfd'?[['packet-shift-y',['П→X','2']]]:[]),
        ...(qMarkerPacket==='yfd'?[['packet-shift-y-old-address',['П→X','Сx']]]:[]),
        ...(packetRank>=9?[
          ['packet-clear-u-prime',['П→X','ВП']],['packet-clear-u',['П→X','ВП']]]:[]),
        ...(packetRank>=10?[['packet-sign',['K','5']]]:[]),
        ...(packetRank>=11?[['packet-sign-retry',['K','5']]]:[]),
        ...(packetRank>=12?[['packet-lastx',['F','В↑']]]:[]),
        ...(packetRank>=13?[['packet-sign-number',['K','5']]]:[]),
        ...(packetFlush>=1?[['packet-flush1',['П→X','5']]]:[]),
        ...(packetFlush>=2?[['packet-flush2',['П→X','5']]]:[]),
        ...(packetFlush>=3?[['packet-flush3',['П→X','5']]]:[]),
        ...(['ynx','yns','ynr','ynb','yc1','yc6','yc6x','yc7','yc7z','ykc','ykm','ykn','ykr','yku','ykv'].includes(qMarkerPacket)?[['packet-lastx-clean',['F','В↑']]]:[]),
        ...(['yns','ynr','ynb','yc1','yc6','yc6x','yc7','yc7z','ykc','ykm','ykn','ykr','yku','ykv'].includes(qMarkerPacket)?[['packet-sign-clean',['K','5']]]:[]),
        ...(['ynr','ynb','yc1','yc6','yc6x','yc7','yc7z','ykc','ykm','ykn','ykr','yku','ykv'].includes(qMarkerPacket)?[
          ['packet-lastx-repeat',['F','В↑']],['packet-sign-repeat',['K','5']]]:[]),
        ...(qMarkerPacket==='ynb'?[['packet-sign-overwrite',['K','5']]]:[]),
        ...(['yc1','yc6','yc6x','yc7','yc7z'].includes(qMarkerPacket)?[['packet-restore-aux0F',['П→X','6']]]:[]),
        ...(['yc6','yc6x','yc7','yc7z'].includes(qMarkerPacket)?[
          ['packet-restore-clone1',['П→X','0']],['packet-restore-clone2',['П→X','0']],
          ['packet-restore-TF',['П→X','/-/']],['packet-restore-X1F',['П→X','7']],
          ['packet-restore-removeP8',['П→X','3']]]:[]),
        ...(['yc6x','yc7','yc7z'].includes(qMarkerPacket)?[['packet-restore-cx',['Сx']]]:[]),
        ...(['yc7','yc7z'].includes(qMarkerPacket)?[['packet-restore-clearX1',['П→X','/-/']]]:[]),
        ...(['ykc','ykm','ykn','ykr','yku','ykv'].includes(qMarkerPacket)?[
          ['packet-clean-zero1',['П→X','5']],['packet-clean-zero2',['П→X','5']],
          ['packet-clean-zero3',['П→X','5']],['packet-clean-zero4',['П→X','5']],
          ['packet-clean-aux0F',['П→X','6']],...(qMarkerPacket==='ykn'?[]:[['packet-clean-port5',['X→П','8']]]),
          ['packet-clean-YF',['П→X','8']],['packet-clean-X1F',['П→X','/-/']],
          ['packet-clean-P8',['П→X','В↑']],
          ['packet-clean-flush1',['П→X','4']],['packet-clean-flush2',['П→X','4']],
          ['packet-clean-flush3',['П→X','4']],['packet-clean-flush4',['П→X','4']],['packet-clean-flush5',['П→X','4']],
          ['packet-clean-port5-zero',['X→П','5']]]:[]),
        ...(['ykm','ykn','ykr','yku','ykv'].includes(qMarkerPacket)?[
          ['packet-clean-cx1',['Сx']],['packet-clean-cx2',['Сx']],['packet-clean-two',['2']],
          ['packet-clean-enter',['В↑']],['packet-clean-three',['3']],['packet-clean-plus',['+']],
          ['packet-clean-store2',['X→П','2']],['packet-clean-register-clear',['Сx']],
          ['packet-clean-read2',['П→X','2']],['packet-clean-register-clear2',['Сx']],
          ['packet-clean-register-zero2',['X→П','2']],['packet-clean-lastx',['F','В↑']],
          ['packet-clean-backup-clear',['Сx']],['packet-clean-backup-zero',['X→П','В↑']]]:[]),
        ...(['ykr','yku','ykv'].includes(qMarkerPacket)?[
          ['packet-reopen-YF',['П→X','ВП']],['packet-reopen-X1F',['П→X','8']],
          ['packet-reopen-WF',['П→X','ВП']],['packet-reopen-P8F',['П→X','3']],
          ['packet-reopen-W0',['П→X','4']],
          qMarkerPacket==='yku'?['packet-reopen-aux0zero-native',['П→X','1']]:['packet-reopen-aux0zero',['П→X','9']],
          ['packet-reopen-Zzero',['X→П','8']],
          ...(['yku','ykv'].includes(qMarkerPacket)?[
            ['packet-reopen-flush1',['П→X','5']],['packet-reopen-flush2',['П→X','5']],
            ['packet-reopen-flush3',['П→X','5']]]:[]),
          ['packet-reopen-lastx',['F','В↑']]]:[]),
        ...packetLateActions.map(([label,keys])=>[label,keys]),
        ...packetSecondActions.map(([label,keys])=>[label,keys]),
        ...secondNormalActions.map(([label,keys])=>[label,keys]),
        ...secondRetainRepeatActions.map(([label,keys])=>[label,keys]),
        ...thirdActions.map(([label,keys])=>[label,keys]),
        ...(qMarkerRepeat?packetRepeatActions.map(([label,keys])=>[label,keys]):[]),
        ['packet-idle',[]]]:[]),
      ...(qRestoreIdleCheck&&qMarkerPacket===null?[['restore-idle',[]]]:[]),
      ...(qRestoreCalcCheck?[
        ['restore-test-cx',['Сx']],['restore-test-two',['2']],
        ['restore-test-enter',['В↑']],['restore-test-three',['3']],['restore-test-plus',['+']]]:[]),
      ...(qControllerZeroAfterCx?[
        ['restore-test-cx',['Сx']],['restore-zero-after-cx',['П→X',qControllerPostCxDigit==='E'?'В↑':'8']],
        ['restore-next-idle',[]]]:[]),
      ...(qTRecoveryProfile==='sign'?[
        ['t-recovery-sign',['K','5']],['t-recovery-idle',[]]]:[]),
      ...(qTRecoveryProfile==='zero'?[
        ['t-recovery-zero1',['П→X',qTZeroDigit==='E'?'В↑':'6']],['t-recovery-idle',[]]]:[]),
      ...(qTRecoveryProfile==='enter'?[
        ['t-recovery-enter1',['В↑']],['t-recovery-idle',[]]]:[]),
      ...(qTRecoveryProfile==='lastx'?[
        ['t-recovery-lastx1',['F','В↑']],['t-recovery-idle',[]]]:[]),
      ...(qControllerPostCalc?[
        ['restore-post-cx',['Сx']],['restore-post-two',['2']],
        ['restore-post-enter',['В↑']],['restore-post-three',['3']],['restore-post-plus',['+']]]:[])]:[];
  for(const [label,keys] of exitActions) {
    stage=label;windows[stage]=[];completed[stage]=false;
    if(label.startsWith('t-recovery-'))tRecoveryControlSeen=false;
    if(label.startsWith('packet-'))packetControlSeen=false;
    if(label==='t-recovery-zero1'&&qTLeadFrames)
      for(const x of [c,plain])x.runFrames(qTLeadFrames);
    // Actual630-tag residue: guard P9+10 -> V after two real560-word frames.
    // No phase/state patch or adaptive action based on the passive trace.
    if(label==='packet-clear-u'&&(qMarkerPacket==='ycl'||packetRank>=10))
      for(const x of [c,plain])x.runFrames(2);
    if(['packet-sign','packet-sign-retry'].includes(label)&&(qMarkerPacket==='ysl'||packetRank>=11))
      for(const x of [c,plain])x.runFrames(2);
    // Calculated24 real idle words: P9-entry residue9 -> U/headerFFF residue3.
    // Six real idle words after the call restore the30-word carrier period;
    // both waits also preserve IR phase84. No tickIndex/state/phase patch.
    if(label==='packet-restore-clearX1'&&qMarkerPacket==='yc7')
      for(const x of [c,plain]){for(let j=0;j<24*42;j++)x.tick();x.updateDisplay();}
    if(label==='payload-exit-run'||label==='payload-readback-run'||label==='packet-program-run')runStopSeen=false;
    // The unpaced RCL samples Q/Z/W and cannot visit aux1/FFF. The six-word
    // trial does NOT repair that route: it ends by making P9/FFF instead.
    // The positive adapter deliberately uses that header, then different
    // RCL operands enter it. Tail24 restores the original30-word phase.
    const pacedFirst=(qMarkerSecondPhase==='p7-first-paced'&&/^packet-second-first[123]$/.test(label))
      ||(firstP9&&label==='packet-second-first-adapter');
    if(pacedFirst)for(const x of [c,plain]){for(let j=0;j<6*42;j++)x.tick();x.updateDisplay();}
    const retainLead=secondRetain?(label.endsWith('normal-retain-clearP8')?12:
      label.endsWith('normal-retain-header')?6:0):0;
    const thirdLead=p7Write3?(label==='packet-third-write-Y'?18:label==='packet-third-write-clear2'?12:
      label==='packet-third-write-clear3'?6:0):0;
    if(retainLead)for(const x of [c,plain]){for(let j=0;j<retainLead*42;j++)x.tick();x.updateDisplay();}
    if(thirdLead)for(const x of [c,plain]){for(let j=0;j<thirdLead*42;j++)x.tick();x.updateDisplay();}
    for(const x of [c,plain])press(x,keys);
    if(thirdLead)for(const x of [c,plain]){for(let j=0;j<(30-thirdLead)*42;j++)x.tick();x.updateDisplay();}
    if(retainLead)for(const x of [c,plain]){for(let j=0;j<(30-retainLead)*42;j++)x.tick();x.updateDisplay();}
    if(pacedFirst)for(const x of [c,plain]){for(let j=0;j<24*42;j++)x.tick();x.updateDisplay();}
    if(label==='packet-restore-clearX1'&&qMarkerPacket==='yc7')
      for(const x of [c,plain]){for(let j=0;j<6*42;j++)x.tick();x.updateDisplay();}
    if(label==='payload-exit-run'||label==='payload-readback-run')
      for(const x of [c,plain]){x.runFrames(60);aligned(x);}
    if(packetIdle(label)||['plain-storage-idle','restore-idle','restore-next-idle','t-recovery-idle'].includes(label))
      for(const x of [c,plain]){x.runFrames(12);aligned(x);}
    assert.deepEqual(dump(c),dump(plain),'fresh observer-free '+label);
    exitStages.push({name:label,keys,...snapshot(c)});
    if(firstFrontier&&(label==='packet-second-read-output'||label.startsWith('packet-second-first')||label.startsWith('packet-normal-')||label.startsWith('packet-reopen-control-')||label.startsWith('packet-program-')||label.startsWith('packet-p7-read-')||label.startsWith('packet-p7-first-')||label.startsWith('packet-p7-repeat-')||label.startsWith('packet-third-')))nativeEndpoints[label]={
      fullBefore:fullState(c),tagsBefore:fullTags(tags),word:word+1,
      numericOwner:[...new Set(tags[3].filter((_,j)=>j%3===1)
        .map(id=>cells[id].area+':'+cells[id].word))]};
    if((qMarkerRepeat||p7Repeat)&&packetIdle(label))nativeIdleStates[label]=structuredClone({
      chips:dump(c),extended:c.extended,angleMode:c.angleMode,powered:c.powered,
      displayDigits:c.displayDigits,displayCommas:c.displayCommas,carrierTags:fullTags(tags)});
  }
  let readbackStable=null;
  if(qReadbackIdleCheck) {
    stage='q-readback-idle';windows[stage]=[];completed[stage]=false;
    for(const x of [c,plain]){x.runFrames(12);aligned(x);}
    assert.deepEqual(dump(c),dump(plain),'fresh observer-free readback idle');
    readbackStable=snapshot(c);
    assert.deepEqual(readbackStable.words,exitStages.at(-1).words);
    assert.deepEqual(readbackStable.registers,exitStages.at(-1).registers);
    assert.deepEqual(readbackStable.program,exitStages.at(-1).program);
  }
  const arithmeticStages=[];
  if(qNormalArithmeticCheck) {
    for(const [label,keys] of [['normal-use-one',['1']],['normal-use-plus',['+']]]) {
      stage=label;windows[stage]=[];completed[stage]=false;
      for(const x of [c,plain])press(x,keys);
      assert.deepEqual(dump(c),dump(plain),'fresh observer-free normal arithmetic '+label);
      arithmeticStages.push({name:label,keys,...snapshot(c)});
    }
  }
  const stages=[];
  if(fifo)for(let i=0;i<4;i++) {
    stage='read-fifo'+(i+1);windows[stage]=[];completed[stage]=false;
    if(i)for(const x of [c,plain])press(x,recipe);
    for(const x of [c,plain])press(x,['В↑','П→X','9',...Array(5).fill('В↑')]);
    assert.deepEqual(dump(c),dump(plain));stages.push({name:'fifo'+(i+1),...snapshot(c)});
  }
  const final=stages.at(-1)||arithmeticStages.at(-1)||readbackStable||exitStages.at(-1)||addressStable||addressed||isolatedStable||cleanupStages.at(-1)||qStable||qLifted||lastX||lifted||reread||read||after;
  if(proof) {
    assert.ok(Object.values(completed).every(Boolean),JSON.stringify(completed));
    for(const records of Object.values(windows))
      assert.ok(records.every((r,i)=>r.keysX.length===42&&r.emitted.length===42
        &&(!i||r.word===records[i-1].word+1)));
  }
  const report={case:fifo?'STOP_F_R9_then_FIFO':'STOP_flag_read_F_then_STORE',qMarkerLateNumber,lateNumberAudit,qMarkerSecondPhase,secondSlotAudit,secondRelocationAudit,bankFootprint,thirdAudit,thirdRestoreAudit,
    zeros,minimal,logical,headerAdjustedRecall,traceSeek,qReadInsteadLastX,qReadDigit,qIdleCheck,qWholeTail,qCleanup,qZeroSource,qFinalIdleCheck,qReserveGhost8,qAddressRead,qAddressIdleCheck,qPayloadExit,qInverseScale,qReadbackIdleCheck,qPlainPayload,qNormalReserve,normalInput,normalWord,qPlainControl,qNormalArithmeticCheck,qRestoreControl,qRestoreIdleCheck,qRestoreCalcCheck,qControllerZeroDigit,qControllerAck,qControllerClearDigit,qControllerZeroAfterCx,qControllerPostCxDigit,qControllerPostCalc,qTRecoveryProfile,qTLeadFrames,qTZeroDigit,qMarkerPacket,qMarkerRepeat,qMarkerRepeatClear,qMarkerRepeatCount,calcAudit,postCalcAudit,tRecoveryAudit,packetAudit,ghostMultiplier,ghostWord,
    ghostPrepared,install,recipe,blank,stopped,after,markerPrepared,extraMarkerPrepared,read,cleared,reread,
    liftPrepared,lifted,lastX,realRemoved,zeroSource,qLifted,qStable,isolatedStable,addressed,addressStable,readbackStable,cleanupStages,exitStages,stages,events,
    arithmeticStages,nativeQMarkerF:final.words.Q[4]==='F',ALL5mirror:true,onlyPublicKeys:true};
  if(log)console.log(JSON.stringify(report));
  hashes();return {report,ghostPrepared,blank,stopped,after,markerPrepared,extraMarkerPrepared,read,cleared,reread,
    liftPrepared,lifted,lastX,realRemoved,zeroSource,qLifted,qStable,isolatedStable,addressed,addressStable,readbackStable,cleanupStages,exitStages,arithmeticStages,stages,events,windows,cells,nativeIdleStates,nativeEndpoints};
}
if(require.main===module) {
  if(process.argv.includes('--stop-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,log:false})));return;
  } else if(process.argv.includes('--read-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,log:false})));return;
  } else if(process.argv.includes('--fifo-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,fifo:true,log:false})));return;
  } else if(process.argv.includes('--clear-read-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,log:false})));return;
  } else if(process.argv.includes('--digit-lift-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,clearDigitLift:true,log:false})));return;
  } else if(process.argv.includes('--lastx-lift-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,clearDigitLift:true,lastXLift:true,log:false})));return;
  } else if(process.argv.includes('--w-lastx-native')) {
    stopTransport({zeros:1,minimal:true,readBack:true,readAgainAfterClear:true,lastXLift:true});
  } else if(process.argv.includes('--q-lift-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,log:false})));return;
  } else if(process.argv.includes('--q-read1-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      log:false})));return;
  } else if(process.argv.includes('--q-read9-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',log:false})));return;
  } else if(process.argv.includes('--q-stable-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qIdleCheck:true,log:false})));return;
  } else if(process.argv.includes('--q-whole-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qIdleCheck:true,qWholeTail:true,log:false})));return;
  } else if(process.argv.includes('--q-clear-v-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qIdleCheck:true,qCleanup:'clear_v',log:false})));return;
  } else if(process.argv.includes('--q-clear-stack-native')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qIdleCheck:true,qCleanup:'clear_v_and_stack',log:false})));return;
  } else if(process.argv.includes('--q-zero-source-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qZeroSource:true,qIdleCheck:true,log:false})));return;
  } else if(process.argv.includes('--q-zero-read0-native')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qZeroSource:true,qIdleCheck:true,qCleanup:'read0_twice',log:false})));return;
  } else if(process.argv.includes('--q-single-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qZeroSource:true,qIdleCheck:true,qWholeTail:true,
      qCleanup:'read2_twice',qFinalIdleCheck:true,log:false})));return;
  } else if(process.argv.includes('--q-address9-proof-input')||process.argv.includes('--q-addressE-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qZeroSource:true,qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',
      qFinalIdleCheck:true,qAddressRead:process.argv.includes('--q-addressE-proof-input')?'E':'9',
      log:false})));return;
  } else if(process.argv.includes('--q-ghost8-native')||process.argv.includes('--q-ghost8-readD-native')
      ||process.argv.includes('--q-ghost8-long-native')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qZeroSource:true,qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',
      qFinalIdleCheck:true,qReserveGhost8:true,
      qAddressRead:process.argv.includes('--q-ghost8-native')?null:'D',
      ghostMultiplier:process.argv.includes('--q-ghost8-long-native')?'1.2345678':'1.0000003',log:false})));return;
  } else if(process.argv.includes('--q-payload-short-proof-input')||process.argv.includes('--q-payload-long-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qZeroSource:true,qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',
      qFinalIdleCheck:true,qReserveGhost8:true,qAddressRead:'D',qAddressIdleCheck:true,
      ghostMultiplier:process.argv.includes('--q-payload-long-proof-input')?'1.2345678':'1.0000003',
      log:false})));return;
  } else if(process.argv.includes('--q-payload-exit-proof-input')||process.argv.includes('--q-payload-program-exit-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,readBack:true,
      readAgainAfterClear:true,lastXLift:true,removeRealThenLastX:true,qReadInsteadLastX:true,
      qReadDigit:'9',qZeroSource:true,qIdleCheck:true,qWholeTail:true,qCleanup:'read2_twice',
      qFinalIdleCheck:true,qReserveGhost8:true,qAddressRead:'D',qAddressIdleCheck:true,
      ghostMultiplier:'1.2345678',
      qPayloadExit:process.argv.includes('--q-payload-program-exit-proof-input')?'program_auto':'auto',log:false})));return;
  } else if(process.argv.includes('--logical-w-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,
      logical:true,log:false})));return;
  } else if(process.argv.includes('--logical-r6-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,
      logical:true,readBack:true,headerAdjustedRecall:true,traceSeek:true,log:false})));return;
  } else if(process.argv.includes('--logical-r9-seek-proof-input')) {
    console.log(JSON.stringify(stopTransport({zeros:1,minimal:true,proof:true,
      logical:true,readBack:true,traceSeek:true,log:false})));return;
  } else if(process.argv.includes('--logical-q-lift-native')) {
    stopTransport({zeros:1,minimal:true,readBack:true,readAgainAfterClear:true,
      lastXLift:true,removeRealThenLastX:true,logical:true});
  } else if(process.argv.includes('--read-exact-marker'))stopTransport({zeros:1,minimal:true,readBack:true});
  else if(process.argv.includes('--minimal-exact-marker'))stopTransport({zeros:1,minimal:true});
  else if(process.argv.includes('--exact-marker'))stopTransport({fifo:true,zeros:1});
  else if(process.argv.includes('--stop-fifo'))stopTransport({fifo:true});
  else if(process.argv.includes('--stop'))stopTransport();
  else if(process.argv.includes('--arrows'))arrowTransport();
  else if(process.argv.includes('--transport')) {
    run('Y_F_swap_store',['Сx','0','0','/','ВП','K','0'],{transport:'swapY'});
    run('X1_F_recall_store',['Сx',...Array(7).fill('0'),'/','ВП','K','0'],{transport:'lastX'});
  } else {
    run('younger2zero',['Сx','0','0','/','ВП','K','0']);
    run('older7zero',['Сx',...Array(7).fill('0'),'/','ВП','K','0']);
    run('logical_blank',['Сx','K','Сx','K','8']);
  }
  console.log('PASS source-selected blank/storage controls, fresh ALL5 mirrors; '
    +'actual marker observations, not symbolic injection; no live test or completeK2 claim.');
}
module.exports={run,arrowTransport,stopTransport};
