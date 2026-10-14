#!/usr/bin/env node
'use strict';
// Native early T-type7 maker. Only keys and frames change the reference;
// guards inherited from ready() prohibit ordinary/program state setters.
// Reapply the MODE/signature tail, NOT the arithmetic programme, after the
// four last-X pushes. A complete native C8/read/digit control follows.
const assert=require('node:assert/strict');
const native=require('./cache-digit-redirect-native.cjs');
const {working}=require('./cache-native-type7-transfers.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const registers=c=>Array.from({length:15},(_,i)=>rawMemoryRegister(c,i));
const seven='700010000005';

function ready() {
  const c=native.ready(),before={program:listing(c),ms:fullMsPages(c),registers:registers(c)};
  assert.equal(working(c).X1,seven);
  for(let i=0;i<4;i++) {
    c.pressSequence(['F','/-/','F','В↑']);aligned(c);
    assert.equal(working(c).X,seven);
    assert.deepEqual(listing(c),before.program);
    assert.deepEqual(fullMsPages(c),before.ms);
    assert.deepEqual(registers(c),before.registers,'last-X pushes hold all15 ordinary words');
  }
  assert.deepEqual(working(c),{X1:seven,X:seven,Y:seven,Z:seven,T:seven});
  // Last-X changes the decoder's mode context. Recreate the native
  // ST32=F/ST35=9 signature without recalculating the stack or resetting it.
  c.pressSequence(['F','/-/']).runFrames(4);
  c.pressSequence(['F','ВП']).runFrames(4);
  c.press('В↑').runFrames(4);
  c.pressSequence(['F','/-/']).runFrames(4);
  for(let i=0;i<2;i++)c.pressSequence(['БП','5','8']).runFrames(4);
  aligned(c);
  assert.equal(c.programCounter(),'58');
  assert.equal(c.ik1302.stack[32],15);
  assert.equal(c.ik1302.stack[35],9);
  assert.deepEqual(working(c),{X1:seven,X:'093050000000',Y:seven,Z:seven,T:seven});
  assert.deepEqual(listing(c),before.program);
  assert.deepEqual(fullMsPages(c),before.ms);
  const changes=registers(c).flatMap((v,i)=>v===before.registers[i]?[]:
    [{register:i,before:before.registers[i],after:v}]);
  assert.deepEqual(changes,[{register:5,before:'007000000001',after:'007000000002'}]);
  assert.equal(rawMemoryRegister(c,10),'600010000003');
  assert.equal(rawMemoryRegister(c,12),'000000000000');
  return c;
}

function capture({mirror=true,log=true}={}) {
  const result=native.capture({prepare:ready,ringProbe:true,mirror,log:false});
  const source=result.metadata.filter(e=>e.command>=result.report.sourceCommand);
  assert.deepEqual(source.map(e=>e.ip),[0xAC,0xC8,0x8C]);
  assert.ok(source.every(e=>e.T34===7&&e.X34===6&&e.X22===1&&e.C24===0));
  result.report={...result.report,nativeEarlyT7:true,nativeXTypeStill6:true,
    ordinaryChangesDuringSignatureRepair:[5],nativeCsign:0,nativeXmarker:1,
    extraXmarkerCreated:false,signFCreated:false,nativeProgramExport:false,partialK2:false};
  if(log)console.log(JSON.stringify({report:result.report,metadata:source}));
  return result;
}
if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(capture({mirror:false,log:false})));
  else {
    capture();
    console.log('PASS keyboard-only early T-type7 maker AND the native C8/read/digit source; '
      +'ALL105 program/56Ms held, fresh ALL5 mirror. C-signF/X-markerF still absent.');
  }
}
module.exports={ready,capture};
