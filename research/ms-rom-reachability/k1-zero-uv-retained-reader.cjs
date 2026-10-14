#!/usr/bin/env node
'use strict';
// Keep original P0 in M1, not in the request header: make real/Z with T=0,
// then use the proved control-side ROLL to read U/V into free stack slots.
// No ordinary register is scratch. No snapshot import or state/ROM edits.
const assert=require('node:assert/strict'),cap=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs'),{ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const base={incoming:'-1.2345678E42',phaseOffset:2,p3:'777',
  values:['811','822','-9.8765432E23','4.44E12'],fullUpper:['9011','9022','9033','9044']};
function operation(c,o,record=()=>{}){
  c.runFrames(o.phaseOffset??2);const a=(s,k,n=8)=>{record(s);c.pressSequence(k).runFrames(n);};
  a('uv-clear',['Сx','В↑','В↑','В↑','+']);
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())a('uv-marker'+i,[k],12);
  for(let i=0;i<2;i++){a('uv-zero'+i,['0']);a('uv-nop'+i,['K','0']);}
  a('uv-read',['F',',']);
}
function check(r){
  const es=r.traced.events,ww=r.traced.writes,start=es.find(e=>e.stage==='uv-read'&&e.ring),end=es.find(e=>e.stage==='done'&&e.ring);
  assert.ok(start&&end);const zero='000000000000',u=r.before.U.slice(2),v=r.before.V.slice(2);
  const originalWords=r.beforeRegisters.concat(Object.values(r.before).map(w=>w.slice(2)));
  assert.equal(originalWords.length,23);
  assert.equal(new Set(originalWords).size,23,'all incoming bank words must be independent in this fixture');
  const visible=e=>['X','Y','Z','T'].map(w=>raw(e.ring[w]));
  assert.deepEqual(visible(start),[zero,zero,'0000F0000000',zero]);
  const source=es.find(e=>e.stage==='uv-read'&&e.ip===0xEE),save=es.find(e=>e.stage==='uv-read'&&e.ip===0xE9),
    request=es.find(e=>e.stage==='uv-read'&&e.ip===0xA3);
  assert.ok(source&&save&&request,'complete native EE/E9/A3 reader path');
  assert.equal(source.slot,'V');assert.equal(source.raw,v);
  assert.equal(save.slot,'X1');
  const expectedSave=ringAt(r,save.command);[...v].reverse().forEach((digit,i)=>{expectedSave.X1[1+3*i]=parseInt(digit,16);});
  assert.deepEqual(ringAt(r,save.command+1),expectedSave,'one exact E9 save of V among all630');
  assert.equal(request.slot,'T');const expectedRequest=ringAt(r,request.command);
  [28,31,34].forEach((n,i)=>{expectedRequest.T[n]=[parseInt(v[2],16),5,2][i];});
  assert.deepEqual(ringAt(r,request.command+1),expectedRequest,'request overwrites only disposable zero header');
  assert.deepEqual(visible(end),[zero,'25'+v[2]+'000000000',v,u]);
  assert.deepEqual(r.afterRegisters,r.beforeRegisters,'all15 incoming ordinary registers held');
  assert.deepEqual(r.after,r.before,'all8 incoming Ms held');assert.deepEqual(r.afterProgram,r.beforeProgram);
  assert.ok(ww.filter(w=>(Object.hasOwn(r.before,w.slot)&&w.nibble%3===1)||w.nibble%3===0||w.nibble%3===2||[37,40].includes(w.nibble))
    .every(w=>w.before===w.value),'all bank/program/service cells held even temporarily');
  assert.deepEqual(Object.keys(end.ring).filter(w=>end.ring[w][22]===15),['marker']);
  return{options:r.options,P0:r.beforeRegisters[0],u,v,visible:visible(end),
    inputDistinctWords:new Set(originalWords).size,all23BankWordsHeld:true,canonicalMarkerOnly:true,
    boundary:'U/V copies in visible Z/T without register scratch; no reverse write or full K1'};
}
function run(o={}){return cap.run({...base,...o},operation,['uv-read']);}
function verify(o){const r=run(o),result=check(r),plain=cap.prepare(r.options);
  operation(plain,r.options);plain.runFrames(3);aligned(plain);
  assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)), 'fresh full observer-free native mirror');
  r.traced.events.length=r.traced.writes.length=0;return result;}
if(require.main===module)console.log(JSON.stringify(verify(process.argv[2]?JSON.parse(process.argv[2]):{})));
module.exports={base,operation,run,check,verify};
