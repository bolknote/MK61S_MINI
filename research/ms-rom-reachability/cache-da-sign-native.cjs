#!/usr/bin/env node
'use strict';
// ROM-directed sign-entry controls. The native A selector is positive;
// the tested decimal sign sources do NOT enter CE/DA. No state setters.
const assert=require('node:assert/strict');
const {prepare}=require('./cache-da-keyboard.cjs');
const {prepareSelector}=require('./st34-origin-trace.cjs');
const {finishSignature700,rawMemoryRegister,registerKey}=require('./check_ac_signature_keyboard.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {layout}=require('./cache-d4-native-topology.cjs');
const raw=[0,3,9,12,18,21],suffix=['F','Сx','/-/'];
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const specs=fixtures.flatMap(fixture=>[
  {fixture,selector:9,carrier:'0'},
  {fixture,selector:10,carrier:'0'},
  {fixture,selector:10,carrier:'-1'},
]);

function prepareReader({fixture,selector,carrier,fullSource=false}) {
  assert.ok([9,10].includes(selector)&&['0','-1'].includes(carrier));
  const c=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    c[name]=()=>{throw Error('Forbidden state setter: '+name);};
  // Seed ordinary PC BEFORE the abnormal-number preparation. This is a
  // register named C, not a program counter or symbolic carrier. Enter the
  // digit BEFORE /-/: inputNumber processes literal key order, not a signed
  // numeric parser (a leading minus would toggle zero before entering 1).
  c.inputNumber(carrier==='-1'?'1':'0',{clear:true});
  if(carrier==='-1')c.press('/-/');
  c.pressSequence(['X→П',registerKey(12)]);aligned(c);
  const storedC=rawMemoryRegister(c,12);
  assert.equal(storedC,carrier==='0'?'000000000000':'000910000000');
  prepare({fixture,calc:c});
  assert.equal(rawMemoryRegister(c,12),storedC,'native marker preparation preserves ordinary PC');
  const ms=fullMsPages(c);
  prepareSelector(c,{selector});finishSignature700(c);aligned(c);
  assert.equal(rawMemoryRegister(c,12),storedC);
  assert.deepEqual(fullMsPages(c),ms);
  // Optional passive ALL5 source audit. Restart at each AC so the saved
  // window is precisely the last AC→firstC8 route, not an older call.
  let sourceWindow=null,completeSource=null;
  const program=listing(c),t=trace(c,c=>{
    c.pressSequence(['П→X',registerKey(selector)]).runFrames(8);aligned(c);
  },{extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    otherChipsAt:e=>{
      if(fullSource&&completeSource===null) {
        if(e.ip===0xAC)sourceWindow=[];
        if(sourceWindow)sourceWindow.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
        if(e.ip===0xC8)completeSource=sourceWindow;
      }
      return false;
    },
  });
  assert.deepEqual(t.primitives,[0xC8]);
  const at=t.events.findIndex(e=>e.ip===0xC8);
  const ac=t.events.findLastIndex((e,i)=>i<at&&e.ip===0xAC);
  assert.ok(ac>=0);
  const sourceEvents=t.events.slice(ac,at+1);
  assert.ok(sourceEvents.every((e,i)=>!i||e.command===sourceEvents[i-1].command+1));
  if(fullSource) {
    assert.equal(completeSource.length,sourceEvents.length);
    for(let i=0;i<sourceEvents.length;i++) {
      assert.equal(completeSource[i].command,sourceEvents[i].command);
      assert.equal(completeSource[i].ip,sourceEvents[i].ip);
      for(const field of ['r','st','m'])
        assert.deepEqual(completeSource[i].state.ik1302[field],sourceEvents[i][field]);
    }
  }
  const load=sourceEvents.find(e=>e.ip===0xD6);assert.ok(load);
  assert.equal(load.slot,'Y');assert.equal(layout().registerPages.Y,'C');
  const sourceWord=load.m.slice(0,36).filter((_,i)=>i%3===0);
  assert.deepEqual(sourceWord,[...storedC].reverse().map(v=>parseInt(v,16)),
    'the actual M1 source is ordinary PC, not Ms or the pointer PA');
  const sourceSign=sourceWord[8];
  assert.equal(sourceEvents.at(-1).st[25],sourceSign);
  assert.equal(c.ik1302.stack[25],sourceSign);
  assert.equal(c.ik1302.stack[33],selector);
  assert.equal(c.ik1302.stack[35],5);
  const payload=fixture.bytes.slice(3,6).flatMap(v=>[v&15,v>>4]);
  assert.deepEqual(raw.map(k=>c.ik1302.r[k]),payload);
  assert.deepEqual(listing(c),program);assert.deepEqual(fullMsPages(c),ms);
  return {c,program,ms,payload,storedC,sourceSign,sourceEvents,completeSource};
}

function finish(c) {c.pressSequence(suffix);aligned(c);}

function capture(spec,{mirror=true,log=true}={}) {
  const {c,program,ms,payload,storedC,sourceSign,sourceEvents}=prepareReader(spec);
  const t=trace(c,finish,{extraIps:Array.from({length:256},(_,i)=>i),fullState:true});
  const es=t.events,at=es.findIndex(e=>e.ip===0x8C),bf=es.findIndex(e=>e.ip===0xBF);
  const ee=es.findIndex(e=>e.ip===0xEE);
  assert.ok(at>=0&&bf>at&&ee>bf);
  assert.equal(es[at].s1,11);assert.equal(es[at].st[25],sourceSign);
  assert.equal(es[at].st[33],spec.selector);
  assert.equal(es[bf].r[26],sourceSign);
  assert.equal(es[bf+1].ip,0xC0,'decimal0/9 sign cannot take BF→CE');
  assert.equal(es[bf].r[33],spec.selector);
  assert.deepEqual(raw.map(k=>es[bf].r[k]),payload);
  assert.deepEqual(raw.map(k=>es[ee].r[k]),payload);
  assert.ok(!es.slice(at,ee).some(e=>[0xCE,0xCA,0xDA,0xD4,0xD6].includes(e.ip)),
    'the tested sign branch has no writer or D6 before its ordinary-X read');
  assert.ok(!es.slice(at).some(e=>[0xCE,0xCA,0xDA,0xD4].includes(e.ip)));
  assert.notDeepEqual(raw.map(k=>es[ee+1].r[k]),payload,
    'EE already replaces the raw program cache; a later D6 is not the first loss');
  assert.deepEqual(listing(c),program,'ALL105 program bytes held');
  assert.deepEqual(fullMsPages(c),ms,'ALL56 Ms bytes held');
  const final=machineSnapshot(c);
  if(mirror) {
    const plain=prepareReader(spec);finish(plain.c);
    assert.deepEqual(machineSnapshot(plain.c),final,'fresh unobserved ALL5-chip sign control');
    assert.deepEqual(listing(plain.c),program);assert.deepEqual(fullMsPages(plain.c),ms);
  }
  const prefix=es.slice(at,bf+2);
  assert.ok(prefix.every((e,i)=>!i||e.command===prefix[i-1].command+1));
  const report={fixture:spec.fixture.name,selector:spec.selector,
    registerKey:registerKey(spec.selector),carrier:spec.carrier,ordinaryPC:storedC,
    sourceSign,C8_ST25:sourceSign,C8_ST33:spec.selector,C8_ST35:5,
    suffix,atBF_R26:es[bf].r[26],atBF_next:0xC0,
    raw3HeldAtBF:true,ordinaryXReadLater:true,raw3LostAtFirstEE:true,
    D6BeforeFirstEE:false,D6AfterFirstEE:es.slice(ee+1).some(e=>e.ip===0xD6),nativeDA:false,
    all105ProgramBytesHeld:true,all56MsBytesHeld:true,observerIndependent:mirror,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,sourceEvents,prefix};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(
    specs.map(s=>capture(s,{mirror:false,log:false}))));
  else {
    for(const spec of specs)capture(spec);
    console.log('PASS six keyboard-only sign/source controls and six fresh ALL5-chip mirrors; '+
      'native selectorA, real ST25 source0/9 in ordinary PC, BF→C0 not DA.');
  }
}
module.exports={specs,prepareReader,finish,capture};
