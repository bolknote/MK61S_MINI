#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_swap_handoff.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {checkSwapBlock}=require('./check_a8_ms_readout.cjs');
const guard='958912345678';
function checkSuffix(r,word,start,s1,middle,target) {
  const es=r.traced.events,report=p.analyze(r);
  const at=es.findIndex(e=>e.stage==='upper-swap'&&e.ip===0x40);
  assert.ok(at>=0);const first=es[at];
  assert.equal(first.slot,start);assert.equal(first.s1,s1);assert.equal(raw(first.r,0),word);
  const names=['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10'];
  const seq=[0x40,0x41,middle,0x46];
  const slot=()=>names[(names.indexOf(start)+seq.length)%15];
  while(!['marker','V'].includes(slot()))seq.push(0xE5);
  seq.push(0xE5,0xE6,0xE8,0xE7);
  const path=es.slice(at,at+seq.length);
  assert.deepEqual(path.map(e=>[e.ip,e.slot]),seq.map((ip,i)=>[ip,names[(names.indexOf(start)+i)%15]]));
  for(const e of path)if(e.ip===0xE5)assert.equal(e.m[22]===15,['marker','V'].includes(e.slot));
  const block=checkSwapBlock(r,at+seq.length-1,1);
  assert.equal(block.body[0].slot,target);assert.equal(raw(block.body[0].r,0),word);assert.equal(block.after.ip,0x47);
  assert.equal(report.cached.t,17);assert.equal(report.secondaryWrite.t,18);
  assert.equal(report.cached.m,word);assert.equal(report.secondaryWrite.m,word);
  assert.equal(report.acceptedControls[0].t,7);assert.equal(report.acceptedControls[0].slot,'control');
  assert.equal(report.acknowledgement.t,16);
  assert.equal(report.formatter.slot,target);
  return report;
}
function main() {
  const o={stress:true,upperValues:['-1E-99','0','333','444']};
  const zero=p.run(o),z=checkSuffix(zero,'000000000000','P9',0,0x43,'P7');
  assert.equal(z.formatter.t,77);assert.equal(zero.afterRegisters[0],'000000000000');
  console.log('PASS: original zero: control accepted at 7, acknowledgement at 16, stale read at 17, secondary write at 18, destructive formatter at 77; 14-command suffix matches symbolic proof.');
  const protectedCase=p.run({...o,primeKeys:['П→X','4']});
  const g=checkSuffix(protectedCase,guard,'Z',9,0x42,'X');
  assert.equal(g.formatter.t,69);assert.equal(protectedCase.afterRegisters[0],protectedCase.before.P8.slice(2));
  console.log('PASS: guard: same early read, but the 14-command formatter suffix writes X at 69, not Ms P7.');
  const visible=p.run({...o,primeKeys:['Сx','1']});
  assert.equal(visible.afterRegisters[0],'000000000000');
  assert.equal(p.analyze(visible).formatter.slot,'P7');
  assert.ok(visible.traced.events.filter(e=>e.stage==='upper-prime'&&e.ip===0xE7).every(e=>e.slot==='X'));
  console.log('PASS: negative control: typing 1 changes visible X, not the cached Ms source; zero-fifth loss remains.');
  const program=p.run({...o,mode:'program'});
  assert.deepEqual(program.beforeProgram.slice(0,3),[0x14,0xBC,0x50]);
  assert.notEqual(program.afterRegisters[0],program.before.P8.slice(2));
  assert.ok(program.traced.events.some(e=>e.stage==='upper-swap'&&e.ip===0xC9));
  assert.notEqual(program.after.P8,program.before.P7);
  console.log('PASS: negative control: putting 14/BC/50 in user program is not a bypass; C9/program fetch follows displaced markers and no sixth-word backup results.');
  console.log('LIMIT: the two proven suffixes start at native 40 entries; full preparation and secondary timing are native-test obligations.');
}
if(require.main===module)main();
module.exports={checkSuffix};
