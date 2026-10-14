#!/usr/bin/env node
'use strict';
// Passive lifecycle of native address-stack value 46 after the raw reader.
// Fixed keyboard protocols only; observers never choose keys or timing.
const assert=require('node:assert/strict');
const {reader,plainReader}=require('./check_partial_k2_cache_exit.cjs');
const {fixtures}=require('./check_partial_k2_program_scan.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const positions=[0,3,9,12,18,21];
const sp=c=>[0,1,2].map(i=>c.st[36+i]+16*c.st[39+i]);
const hex=n=>n.toString(16).toUpperCase().padStart(2,'0');
const protocols=[
  {name:'F_prefix',keys:['F']},
  {name:'K_prefix',keys:['K']},
  {name:'F_CLEAR',keys:['F','Сx']},
  {name:'F_CLEAR_COMMA',keys:['F','Сx',',']},
  {name:'F_CLEAR_PROGRAM',keys:['F','Сx','F','ВП']},
  {name:'STORE9',keys:['X→П','9']},
];

function capture(protocol=protocols.find(p=>p.name==='F_CLEAR_COMMA'),{fixture=fixtures[1],mirror=false,options={}}={}) {
  const calc=reader(fixture,options),initial=machineSnapshot(calc),payload=positions.map(n=>calc.ik1302.r[n]);
  const result=trace(calc,c=>{c.pressSequence(protocol.keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,i)=>i),fullState:true});
  const events=result.events,changes=[];
  for(let i=0;i+1<events.length;i++) {
    const e=events[i],next=events[i+1],before=sp(e),after=sp(next);
    if(before.join()!==after.join()) changes.push({command:e.command,ip:e.ip,next:next.ip,before,after,
      vector:e.r[37]+16*e.r[40],r38:e.r[38],r2:e.r[2],r23:e.r[23],
      cacheA:positions.map(n=>e.r[n]),key:[e.keyX,e.keyY]});
  }
  const pushes=changes.filter(e=>e.ip===0x45&&e.after[0]===0x46);
  assert.ok(pushes.length,'selected native prefix creates the 46 return address');
  const lifecycle=pushes.map(push=>{
    const at=changes.indexOf(push),following=changes.slice(at+1);
    const discard=following.find(e=>e.before.includes(0x46)&&!e.after.includes(0x46));
    return {push,changes:discard?changes.slice(at,changes.indexOf(discard)+1):changes.slice(at),discard:discard||null};
  });
  const firstEE=events.find(e=>e.ip===0xEE),reached46=events.filter(e=>e.ip===0x46);
  for(const x of lifecycle) {
    assert.ok(x.discard,'each recorded native 45-created 46 is discarded');
    assert.deepEqual(x.changes.slice(0,3).map(e=>e.ip),[0x45,0x8B,0x48]);
    assert.deepEqual(x.changes.slice(0,3).map(e=>e.after.indexOf(0x46)),[0,1,2]);
    for(const e of x.changes) assert.deepEqual(e.cacheA,payload,'original cache A survives to 46 discard');
  }
  const intactAt46=reached46.filter(e=>positions.map(n=>e.r[n]).join()===payload.join());
  assert.equal(intactAt46.length,0,'no selected native continuation reaches 46 with original cache A');
  const beforeFirstEE=events.filter(e=>!firstEE||e.command<=firstEE.command);
  assert.equal(beforeFirstEE.filter(e=>e.ip===0x38).length,0,
    'selected keyboard prefixes do not execute the program-vector dispatch 38 before EE');
  if(mirror) {
    const plain=plainReader(fixture,options);plain.pressSequence(protocol.keys);aligned(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc),'fresh complete unobserved native mirror');
  }
  const important=events.filter(e=>[0x45,0x46,0x48,0x38,0x3A,0x8B,0x8C,0x8D,0x98,0xDC,0xEE].includes(e.ip));
  return {calc,initial,events,changes,lifecycle,report:{name:protocol.name,keys:protocol.keys,
    lifecycle:lifecycle.map(x=>({push:{...x.push,ip:hex(x.push.ip),next:hex(x.push.next),
      before:x.push.before.map(hex),after:x.push.after.map(hex),vector:hex(x.push.vector)},
      transitions:x.changes.map(e=>({command:e.command,ip:hex(e.ip),next:hex(e.next),
        before:e.before.map(hex),after:e.after.map(hex),vector:hex(e.vector),r38:e.r38,r2:e.r2,
        cacheHeldA:positions.map(n=>payload[positions.indexOf(n)]).join()===e.cacheA.join()})),
      discardedBy:x.discard?hex(x.discard.ip):null})),
    firstEE:firstEE?{command:firstEE.command,sp:sp(firstEE).map(hex)}:null,
    reached46:reached46.length,intactCacheAt46:intactAt46.length,dispatch38BeforeEE:0,observerIndependent:mirror,
    important:important.slice(0,50).map(e=>({command:e.command,ip:hex(e.ip),sp:sp(e).map(hex),
      vector:hex(e.r[37]+16*e.r[40]),r38:e.r[38],r2:e.r[2],s1:e.s1})),partialK2:false}};
}
if(require.main===module) {
  if(process.argv.includes('--proof-input')) {
    const r=capture(),command=r.lifecycle[0].push.command;
    console.log(JSON.stringify({scope:'native F-prefix 45-created 46 through its B9 discard',
      initial:r.initial.ik1302,events:r.events.filter(e=>e.command>=command&&e.command<=command+6)}));
  }
  else {
    for(const p of protocols) {
      const r=capture(p,{mirror:p.name==='F_CLEAR_COMMA'});
      console.log(JSON.stringify({name:p.name,keys:p.keys,
        pushes:r.lifecycle.length,discardedBy:r.report.lifecycle.map(x=>x.discardedBy),
        cacheHeldAtEachDiscard:true,firstEE:r.report.firstEE,reached46:r.report.reached46,
        intactCacheAt46:r.report.intactCacheAt46,dispatch38BeforeEE:0,
        observerIndependent:r.report.observerIndependent,partialK2:false}));
    }
    console.log('PASS: six selected native prefix protocols; nine native 45-created 46 lifecycles; '+
      'one complete unobserved comma-continuation mirror. No cache-preserving 46 was reached here.');
  }
}
module.exports={capture,protocols,sp};
