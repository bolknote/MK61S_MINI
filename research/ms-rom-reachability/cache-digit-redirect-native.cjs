#!/usr/bin/env node
'use strict';
// One keyboard-only negative. Capture a continuous lastAC→reader→digit
// inlet without rebasing the physical ring between the two traces.
// Constant-IP/key segments are merely a compact passive representation;
// the symbolic replay must prove any skipped full-state periods itself.
const assert=require('node:assert/strict');
const {prepare}=require('./cache-da-keyboard.cjs');
const {prepareSelector}=require('./st34-origin-trace.cjs');
const {finishSignature700,rawMemoryRegister,registerKey}=require('./check_ac_signature_keyboard.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {layout}=require('./cache-d4-native-topology.cjs');
const raw=[0,3,9,12,18,21],suffix=['F','Сx','1'];
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));

function ready() {
  const c=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    c[name]=()=>{throw Error('Forbidden state setter: '+name);};
  c.inputNumber('0',{clear:true}).pressSequence(['X→П',registerKey(12)]);
  aligned(c);prepare({fixture:fixtures[1],calc:c});
  assert.equal(rawMemoryRegister(c,12),'000000000000');
  prepareSelector(c,{selector:10});finishSignature700(c);aligned(c);
  assert.equal(rawMemoryRegister(c,12),'000000000000');
  return c;
}

function finish(c) {
  c.pressSequence(['П→X',registerKey(10)]).runFrames(8);aligned(c);
  c.pressSequence(suffix);aligned(c);
}

function capture({mirror=true,log=true,prepare=ready,ringProbe=false}={}) {
  const c=prepare(),program=listing(c),ms=fullMsPages(c);
  let segments=[],source=[],seenC8=false,started=false,inlet=null;
  const prefix=[];let releaseCount=null;
  const t=trace(c,finish,{
    extraIps:Array.from({length:256},(_,i)=>i),
    ringAt:ringProbe?e=>[0xAC,0xC8,0x8C].includes(e.ip):undefined,
    otherChipsAt:e=>{
      if(!seenC8&&e.ip===0xAC) {segments=[];source=[];started=true;}
      if(!started)return false;
      const current={ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)};
      if(!seenC8)source.push(current);
      if(e.ip===0xC8)seenC8=true;
      if(seenC8&&e.ip===0x8C&&inlet===null)inlet=current;
      if(inlet===null) {
        const pins=Object.fromEntries(['ik1302','ik1303','ik1306'].map(name=>[
          name,[current.state[name].keyX,current.state[name].keyY],
        ]));
        const key=JSON.stringify([e.ip,pins]),previous=segments.at(-1);
        if(previous?.key===key)previous.steps++;
        else segments.push({key,ip:e.ip,pins,start:current,steps:1});
      } else {
        if(prefix.length<65)prefix.push(current);
        if(releaseCount===null&&current.state.ik1302.keyY===0)
          releaseCount=e.command-inlet.command;
      }
      return false;
    },
  });
  assert.deepEqual(t.primitives,[0xC8]);
  assert.equal(source.length,122);
  assert.equal(source[0].ip,0xAC);assert.equal(source.at(-1).ip,0xC8);
  assert.ok(source.every((e,i)=>!i||e.command===source[i-1].command+1));
  assert.equal(prefix.length,65);
  assert.ok(prefix.every((e,i)=>!i||e.command===prefix[i-1].command+1));
  assert.equal(inlet.state.ik1302.st[25],0);
  assert.equal(inlet.state.ik1302.r[41],0);
  assert.deepEqual(raw.map(k=>inlet.state.ik1302.r[k]),[3,10,4,13,5,11]);
  assert.equal(releaseCount,536);
  assert.equal(segments.reduce((n,s)=>n+s.steps,0),inlet.command-source[0].command);
  assert.deepEqual(listing(c),program);assert.deepEqual(fullMsPages(c),ms);
  if(mirror) {
    const plain=prepare();finish(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c));
  }
  const report={sourceCommand:source[0].command,inletCommand:inlet.command,
    sourceToInletMacros:inlet.command-source[0].command,
    segments:segments.length,releaseCount,ST25:0,R41:0,
    all105ProgramBytesHeld:true,all56MsBytesHeld:true,
    observerIndependent:mirror,nativeProgramExport:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  const metadata=ringProbe?t.events.filter(e=>[0xAC,0xC8,0x8C].includes(e.ip)).map(e=>({
    ip:e.ip,command:e.command,T34:e.ring.T[34],X34:e.ring.X[34],
    X22:e.ring.X[22],C24:e.ring.Y[24],
  })):undefined;
  return {report,segments:segments.map(({key,...segment})=>segment),source,prefix,mapping:layout(),
    ...(ringProbe?{metadata}:{})};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))
    console.log(JSON.stringify(capture({mirror:false,log:false})));
  else {
    capture();
    console.log('PASS continuous keyboard-only reader/digit control and fresh ALL5 mirror; '
      +'no native signF, metadata injection or program export.');
  }
}
module.exports={ready,finish,capture};
