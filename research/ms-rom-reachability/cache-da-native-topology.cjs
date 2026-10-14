#!/usr/bin/env node
'use strict';
// Observe only the existing keyboard PC00 controls. All positive DA states
// are created separately in Z3, NEVER assigned to this reference machine.
const assert=require('node:assert/strict');
const {setup}=require('./cache-st24-call00-frontier.cjs');
const {trace}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {specs,finish}=require('./cache-st24-indirect-tail.cjs');
const {layout}=require('./cache-d4-native-topology.cjs');
const call=specs.find(s=>s.name==='call');
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));

function capture({pointer='9',mirror=true,log=true}={}) {
  assert.ok(['9','-9'].includes(pointer),'two existing source controls only');
  const c=setup({pointer}),program=listing(c),ms=fullMsPages(c),prefix=[];
  let collecting=false;
  const t=trace(c,c=>finish(c,call),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    otherChipsAt:e=>{
      if(e.ip===0x73&&!prefix.length)collecting=true;
      if(collecting&&prefix.length<65)
        prefix.push({ip:e.ip,command:e.command,slot:e.slot,state:machineSnapshot(c)});
      return false;
    },
  });
  assert.equal(prefix.length,65);
  assert.ok(prefix.every((e,i)=>!i||e.command===prefix[i-1].command+1));
  const dispatch=t.events.findIndex(e=>e.ip===0x73);
  const gate=t.events.findLastIndex((e,i)=>i<dispatch&&e.ip===0x26);
  assert.ok(gate>=2);
  const origin=t.events.slice(gate-2,dispatch+5);
  assert.deepEqual(origin.map(e=>e.ip),[0xDD,0xD4,0x26,0x28,0x7E,0x73,0x75,0xCA,0xDB,0xDC]);
  assert.ok(origin.every((e,i)=>!i||e.command===origin[i-1].command+1));
  assert.equal(origin[0].sp[0],0x26);
  assert.equal(origin[0].r[3],0);
  assert.equal(origin[2].r[0],origin[0].r[3]);
  assert.equal(origin[5].r[33],origin[0].r[3]);
  assert.deepEqual(fullMsPages(c),ms);
  const after=listing(c),changes=program.flatMap((before,address)=>
    before===after[address]?[]:[{address,before,after:after[address]}]);
  assert.deepEqual(changes,[{address:38,before:0,after:0xF8},{address:39,before:0,after:0x0A}]);
  if(mirror) {
    const plain=setup({pointer});finish(plain,call);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),'ALL5-chip unobserved mirror');
    assert.deepEqual(listing(plain),after);
    assert.deepEqual(fullMsPages(plain),ms);
  }
  const report={pointer,preDD_R3:0,at26_R0:0,at73_R33:0,
    nativeBranch:'DB',nativeDCHeader:3,programChanges:changes,
    all56MsBytesHeld:true,observerIndependent:mirror,
    nativeCacheExport:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,mapping:layout(),origin,prefix};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify(
    ['9','-9'].map(pointer=>capture({pointer,mirror:false,log:false}))));
  else {
    for(const pointer of ['9','-9'])capture({pointer});
    console.log('PASS two native DD/26/R33 origins and two ALL5-chip mirrors; '+
      'DA still NOT reached, existing program damage38/39 explicit.');
  }
}
module.exports={capture};
