#!/usr/bin/env node
'use strict';
// Eight source-directed indirect operations with the SAME ordinary P8=9.
// Native controls only. No hypothetical R26/ST24 values enter the machine.
const assert=require('node:assert/strict');
const {prepare}=require('./cache-st24-native-source.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const specs=[
  {name:'recall',key:'П→X',type:13,kind:0,handler:0x70,next:0xAB,reader:true},
  {name:'store',key:'X→П',type:11,kind:1,handler:0x71,next:0xAA,reader:false},
  {name:'goto',key:'БП',type:8,kind:2,handler:0x72,next:0x74,reader:false},
  {name:'call',key:'ПП',type:10,kind:3,handler:0x73,next:0x6F,reader:false},
  {name:'x_ne_0',key:'С/П',type:7,abort:true,reader:false},
  {name:'x_ge_0',key:'В/О',type:9,abort:true,reader:false},
  {name:'x_lt_0',key:'ШГ→',type:12,kind:2,handler:0x72,next:0x74,reader:false},
  {name:'x_eq_0',key:'ШГ←',type:14,kind:2,handler:0x72,next:0x74,reader:false},
];
const listing=c=>Array.from({length:105},(_,i)=>c.readCommand(i));
const raw=e=>[0,3,9,12,18,21].map(k=>e.r[k]);

function finish(c,spec) {
  c.pressSequence(['K',spec.key,'8']).runFrames(8);aligned(c);
  c.pressSequence(['F','Сx',',']);aligned(c);
}

function capture(spec,{mirror=true,log=true}={}) {
  const c=prepare(),ms=fullMsPages(c),program=listing(c);
  const t=trace(c,c=>finish(c,spec),{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
  });
  const es=t.events,ab=es.findIndex(e=>e.ip===0xAB);
  assert.ok(ab>=0);assert.equal(es[ab].r[35],spec.type);
  assert.equal(es[ab+1].ip,0xA5);assert.equal(es[ab+1].r[26],15);
  const dispatch=es.findIndex((e,i)=>i>ab&&e.ip===(spec.abort?0x27:0x7E));
  assert.ok(dispatch>ab);assert.equal(es[dispatch].r[26],15);
  if(spec.abort) {
    assert.equal(es[dispatch+1].ip,0x29);
    assert.equal(es[dispatch+2].ip,0xD3);
    assert.equal(es[dispatch+2].r[26],0);
  } else {
    assert.equal(es[dispatch].r[35],spec.kind);
    assert.equal(es[dispatch].s1,14);
    assert.equal(es[dispatch+1].ip,spec.handler);
    assert.equal(es[dispatch+2].ip,spec.next);
  }
  const ac=es.findIndex((e,i)=>i>dispatch&&e.ip===0xAC);
  assert.ok(ac>dispatch);assert.equal(es[ac].r[26],0);
  if(!spec.abort&&spec.kind<=1) {
    assert.equal(es[dispatch+2].r[33],4,'normalizer builds ordinary command header4');
    assert.equal(es[dispatch+2].r[35],6,'S1=E makes the ordinary operand6');
    if(spec.kind===0) {
      assert.equal(es[dispatch+3].ip,0xAD);
      assert.equal(es[dispatch+4].r[26],0,'recall AD clearsF');
    } else assert.equal(es[dispatch+3].ip,0xE5,'store AA/type4 is NOT AC');
  } else if(!spec.abort) {
    const reset=es.findIndex((e,i)=>i>dispatch&&i<ac&&e.ip===0x86);
    assert.ok(reset>dispatch);assert.equal(es[reset+1].r[26],0);
    if(spec.kind===3)assert.equal(es[dispatch+3].ip,0x62);
  }
  const reads=es.filter(e=>e.ip===0xC8);
  assert.equal(reads.length,spec.reader?1:0);
  if(spec.reader) {
    assert.equal(reads[0].st[24],0);
    const dc=es.findLast(e=>e.ip===0xDC);assert.ok(dc);
    assert.equal(dc.r[25],0);assert.equal(dc.r[34],15);
    assert.deepEqual(raw(dc),[3,10,4,13,5,11]);
  }
  assert.deepEqual(fullMsPages(c),ms,'all56 Ms bytes held');
  assert.deepEqual(listing(c),program,'all105 program bytes held');
  assert.equal(c.ik1302.r[36]+16*c.ik1302.r[39],0x35);
  const beforeReader=es.slice(ab,dispatch+1);
  const earlierD4=beforeReader.filter(e=>e.ip===0xD4);
  assert.equal(earlierD4.length,spec.abort?0:1);
  for(const e of earlierD4)assert.deepEqual(raw(e),[0,0,0,0,0,0],
    'native address-resolution D4 is NOT exporting the later program cache');
  const proofEvents=es.slice(ab,ac+1);
  assert.ok(proofEvents.every((e,i)=>!i||e.command===proofEvents[i-1].command+1));
  if(mirror) {
    const plain=prepare();finish(plain,spec);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(c),
      'fresh unobserved fixed keys reproduce all5 chip states/ports');
  }
  const report={operation:spec.name,keys:['K',spec.key,'8'],pointer:9,
    nativeABCreatesF:true,kind:spec.kind,handler:spec.handler,
    handlerNext:spec.next,AC_R26:0,programReaderReached:spec.reader,
    skippedCondition:!!spec.abort,
    all56MsBytesHeld:true,all105ProgramBytesHeld:true,
    earlierNativeD4Count:earlierD4.length,
    earlierNativeD4IsAddressResolution:earlierD4.length>0,observerIndependent:mirror,
    nativeCacheExport:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,proofEvents};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))
    console.log(JSON.stringify(specs.map(s=>capture(s,{mirror:false,log:false}))));
  else {
    for(const s of specs)capture(s);
    console.log('PASS eight ROM-directed native indirect controls and eight fresh ALL5-chip mirrors; '+
      'none transports AB F into the required cache metadata. Not an exhaustive keyboard exclusion.');
  }
}
module.exports={specs,finish,capture};
