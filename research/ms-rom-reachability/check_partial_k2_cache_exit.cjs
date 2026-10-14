#!/usr/bin/env node
'use strict';
// ROM-directed continuation checks, NOT an exhaustive keyboard search.
// No continuation obtains its keys or timing from a state observer.
const assert=require('node:assert/strict');
const {fixtures,install}=require('./check_partial_k2_program_scan.cjs');
const {run,preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {prepareCombined,finishCombined}=require('./check_ac_signature_keyboard.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const value='8.7654321E-91';
const positions=[0,3,9,12,18,21];
const hex=a=>a.map(n=>n.toString(16).toUpperCase()).join('');
const lane=(a,n)=>a.filter((_,i)=>i%3===n).slice(0,12);
const protocols=[
  {name:'F_prefix',keys:['F'],read:false},
  {name:'AUTO',keys:['F','/-/'],read:true},
  {name:'STORE9',keys:['X→П','9'],read:true},
  {name:'indirect_STORE5',keys:['K','X→П','5'],read:true},
  {name:'digit1',keys:['1'],read:true},
];

function reader(f=fixtures[1],options={}) {
  const result=run(value,{...options,prepareProgram:c=>install(c,f)});
  assert.deepEqual(positions.map(n=>result.calc.ik1302.r[n]),
    f.bytes.slice(3,6).flatMap(n=>[n&15,n>>4]));
  return result.calc;
}

function plainReader(f,options={}) {
  const calc=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw Error('Forbidden host setter: '+name);};
  install(calc,f);preparePayload(value,calc);prepareCombined({calc,counter:1});
  calc.runFrames(options.phaseOffset||0);finishCombined(calc,options);aligned(calc);
  return calc;
}

function capture(protocol,f=fixtures[1],{mirror=true}={}) {
  const calc=reader(f),initial=machineSnapshot(calc),ms=fullMsPages(calc);
  const payload=positions.map(n=>calc.ik1302.r[n]);
  let seenEE=false;
  const primaryWritesBeforeEE=[];
  const result=trace(calc,c=>{c.pressSequence(protocol.keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true,
    eventFilter:ip=>{if(ip===0xEE)seenEE=true;return true;},
    onWrite:w=>{if(!seenEE&&w.chip===3)primaryWritesBeforeEE.push(w);},
  });
  const events=result.events,readAt=events.findIndex(e=>e.ip===0xEE);
  assert.equal(readAt>=0,protocol.read);
  const before=readAt<0?events:events.slice(0,readAt+1);
  assert.ok(before.length);
  for(const e of before)
    assert.deepEqual(positions.map(n=>e.r[n]),payload,
      `original three-byte cache held before ${e.ip.toString(16)}`);
  assert.deepEqual(primaryWritesBeforeEE,[],'no primary ring write precedes the first EE');
  assert.ok(!before.some(e=>[0x40,0x93,0x98,0xEC,0xE7,0xA8,0xBC,0xD4].includes(e.ip)),
    'no whole-word buffer save or numeric writer before the first EE');
  let read=null;
  if(readAt>=0) {
    const ee=events[readAt],after=events[readAt+1];
    assert.ok(after&&after.command===ee.command+1);
    assert.equal(ee.slot,'X');
    assert.deepEqual(lane(after.r,0),lane(ee.m,1),'EE replaces A by ordinary X (M2), not program cache');
    read={command:ee.command,slot:ee.slot,beforeA:hex(lane(ee.r,0)),
      afterA:hex(lane(after.r,0)),next:after.ip.toString(16).toUpperCase()};
  } else {
    assert.deepEqual(positions.map(n=>calc.ik1302.r[n]),payload);
    assert.deepEqual(fullMsPages(calc),ms,'F prefix alone holds the complete Ms bank');
  }
  if(mirror) {
    const plain=plainReader(f);plain.pressSequence(protocol.keys);aligned(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc),
      'fresh complete unobserved native mirror, with fixed inputs and waits');
  }
  const sequence=[];
  for(const e of before)if(sequence.at(-1)!==e.ip)sequence.push(e.ip);
  return {initial:initial.ik1302,preEEIps:[...new Set(before.map(e=>e.ip))],
    report:{name:protocol.name,keys:protocol.keys,read,
      route:sequence.map(n=>n.toString(16).toUpperCase()).join(' '),
      noPrimaryWriteBeforeEE:true,observerIndependent:mirror,partialK2:false}};
}

if(require.main===module) {
  const results=protocols.map(p=>capture(p,fixtures[1],
    {mirror:!process.argv.includes('--proof-input')}));
  if(process.argv.includes('--proof-input'))console.log(JSON.stringify({
    scope:'five selected exits, not all possible keyboard paths',
    initial:results[0].initial,
    preEEIps:[...new Set(results.flatMap(r=>r.preEEIps))].filter(n=>n!==0xEE),
    reports:results.map(r=>r.report),
  }));
  else {
    for(const r of results)console.log(JSON.stringify(r.report));
    console.log('PASS: five native cache continuations and five complete fresh mirrors. '+
      'F holds the cache; four selected actions reread X before saving/writing it. Not partial K2.');
  }
}
module.exports={reader,plainReader,capture,protocols};
