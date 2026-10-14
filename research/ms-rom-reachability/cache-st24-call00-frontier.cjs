#!/usr/bin/env node
'use strict';
// Native PC00 variant of the otherwise identical indirect-call control.
// This intentionally audits damage in a DISPOSABLE reference instance:
// it is not a cache export, not a safe keyboard recipe for a physical device.
const assert=require('node:assert/strict');
const {prepare}=require('./cache-st24-native-source.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {specs,finish}=require('./cache-st24-indirect-tail.cjs');
const call=specs.find(s=>s.name==='call');
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));

function setup({pointer='9'}={}) {
  const c=prepare({pointer});c.pressSequence(['БП','0','0']).runFrames(4);aligned(c);
  assert.equal(c.programCounter(),'00');return c;
}

function capture({pointer='9',mirror=true,log=true}={}) {
  assert.ok(['9','-9'].includes(pointer),'two source-directed signed controls only');
  const c=setup({pointer}),program=listing(c),ms=fullMsPages(c);
  const t=trace(c,c=>finish(c,call),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
  });
  assert.deepEqual(t.primitives,[],'no program cache reader in this control');
  const start=t.events.findIndex(e=>e.ip===0x73);
  assert.ok(start>=0);
  const frontier=t.events.slice(start,start+5);
  assert.deepEqual(frontier.map(e=>e.ip),[0x73,0x75,0xCA,0xDB,0xDC]);
  assert.equal(frontier[0].pc,0);assert.equal(frontier[0].r[26],15);
  assert.equal(frontier[2].sp[0],0x76);
  assert.equal(frontier[4].sp[0],0x76);
  assert.equal(frontier[4].r[26],15);
  assert.equal(frontier[4].r[34],3,'native DC header is3, NOT4');
  assert.equal(t.events[start+5].ip,0xDE);
  assert.equal(t.events[start+6].ip,0xD3);
  assert.equal(t.events[start+6].r[26],0,'DE clearsF before the selected D3');
  const after=listing(c),changes=program.flatMap((before,address)=>
    before===after[address]?[]:[{address,before,after:after[address]}]);
  assert.deepEqual(changes.map(e=>e.address),[38,39],
    'explicit damaged-program control: do NOT claim full program preservation');
  assert.deepEqual(changes,[{address:38,before:0,after:0xF8},{address:39,before:0,after:0x0A}]);
  assert.deepEqual(fullMsPages(c),ms,'all56 Ms bytes held');
  assert.equal(c.ik1302.r[36]+16*c.ik1302.r[39],0x35);
  if(mirror) {
    const plain=setup({pointer});finish(plain,call);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),
      'fresh unobserved PC00 control reproduces all5 chip states/ports');
    assert.deepEqual(listing(plain),after);
    assert.deepEqual(fullMsPages(plain),ms);
  }
  const report={setupKeys:['БП','0','0'],operation:['K','ПП','8'],pointer,
    nativeCall75:true,nativeDCWithF:true,nativeDCHeader:3,returnTag:0x76,
    DEClearsF:true,programChanges:changes,all56MsBytesHeld:true,
    observerIndependent:mirror,programReaderReached:false,
    nativeCacheExport:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,frontier};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(
    ['9','-9'].map(pointer=>capture({pointer,mirror:false,log:false}))));
  else {
    for(const pointer of ['9','-9'])capture({pointer});
    console.log('PASS two native PC00 signed controls and two fresh ALL5-chip mirrors; '+
      'program damage38/39 is explicit, NO cache export or partialK2.');
  }
}
module.exports={setup,capture};
