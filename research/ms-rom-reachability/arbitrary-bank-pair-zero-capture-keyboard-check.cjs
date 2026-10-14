#!/usr/bin/env node
'use strict';
// Strict native public-key contract for the new half-pair. No calculator
// reads, setters or diagnostic alignment can be used by the key body.
const assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const candidate=require('./arbitrary-bank-pair-zero-capture.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const files=['/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs','/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs',
  ...['ik1302_symbolic.py','analyze_gates.py','audit_ms_rom_control.py','k1-formatter-entry-audit.py'].map(n=>__dirname+'/'+n)];
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const frozen=Object.fromEntries(files.map(p=>[p,hash(p)]));
function guarded(c){
  const counts={keys:0,extraFrames:0};let proxy;
  const allowed=new Set(['press','pressSequence','runFrames']);
  const forbidden=()=>{throw Error('Forbidden calculator reflection/state access');};
  proxy=new Proxy(c,{get(target,name){
    assert.ok(allowed.has(name),'protocol attempted calculator read: '+String(name));
    return(...args)=>{
      if(name==='press')counts.keys++;
      if(name==='pressSequence')counts.keys+=args[0].length;
      if(name==='runFrames')counts.extraFrames+=args[0];
      target[name](...args);return proxy;
    };
  },set:forbidden,getOwnPropertyDescriptor:forbidden,defineProperty:forbidden,
    deleteProperty:forbidden,ownKeys:forbidden,getPrototypeOf:forbidden,setPrototypeOf:forbidden,
    has:forbidden,isExtensible:forbidden,preventExtensions:forbidden});
  return{proxy,counts};
}
function checkGuard(){
  const target={secret:17,press(){return this;},pressSequence(){return this;},runFrames(){return this;}},g=guarded(target);
  assert.equal(g.proxy.press('0'),g.proxy);assert.equal(g.proxy.pressSequence(['K','0']),g.proxy);
  assert.equal(g.proxy.runFrames(8),g.proxy);assert.deepEqual(g.counts,{keys:3,extraFrames:8});
  for(const access of [()=>g.proxy.secret,()=>{g.proxy.secret=18;},
    ()=>Object.getOwnPropertyDescriptor(g.proxy,'secret'),()=>Reflect.ownKeys(g.proxy),
    ()=>Object.defineProperty(g.proxy,'secret',{value:18}),()=>{delete g.proxy.secret;},
    ()=>Object.getPrototypeOf(g.proxy),()=>Object.setPrototypeOf(g.proxy,{}),
    ()=>'secret' in g.proxy,()=>Object.isExtensible(g.proxy),()=>Object.preventExtensions(g.proxy)])
    assert.throws(access,/calculator|protocol/i);
  assert.equal(target.secret,17);
}
const base={p3:'777',values:['811','822','-9.8765432E23','4.44E12'],fullUpper:['9011','9022','9033','9044']};
const cases=[...['1.2345678E42','-1.2345678E42'].flatMap(incoming=>[0,1,2].map(phaseOffset=>({incoming,phaseOffset}))),
  {incoming:'-1.234E-42',phaseOffset:2},{incoming:'0',phaseOffset:2}];
function main(){
checkGuard();
if(process.argv.includes('--guard-only')){console.log('PASS public-key proxy denies direct and reflective state access');return;}
const results=[];
for(const test of cases){
  const options={...base,...test},r=candidate.run(options),audit=candidate.check(r);
  assert.equal(audit.inputDistinctWords,23,'all 23 incoming values must be distinct');
  const plain=cap.prepare(options),g=guarded(plain);
  candidate.operation(g.proxy,options);
  assert.equal(g.counts.keys,23);
  assert.equal(g.counts.extraFrames,136+options.phaseOffset);
  plain.runFrames(3);aligned(plain);
  assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)),
    'fresh unobserved key-only run equals complete native traced state');
  results.push({...test,p:audit.p,v:audit.v,all23Live:audit.all23Live,keys:g.counts.keys,
    bodyFrames:2*g.counts.keys+g.counts.extraFrames});
  r.traced.events.length=r.traced.writes.length=0;
  console.log('PASS strict zero-source capture',JSON.stringify(results.at(-1)));
}
for(const [p,h] of Object.entries(frozen))assert.equal(hash(p),h,'frozen source changed');
console.log(JSON.stringify({cases:results.length,frozenSixUnchanged:true,
  boundary:'23-independent-value half-pair; P0 holds V, original P0 is retained in T, marker Z remains. Reverse write/clean exit/eight-pair K1 are not proven.'}));
}
if(require.main===module)main();
module.exports={guarded,checkGuard,main};
