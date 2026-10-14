#!/usr/bin/env node
'use strict';
// Native trace first; then a separately labelled, host-seeded three-command
// counterfactual. The latter is NOT a key sequence or a successful K2.
const assert = require('node:assert/strict');
const {run,fullMsPages} = require('./probe_c8_payload.cjs');
const {MK61} = require('./paused_keyboard_state.cjs');
const {aligned} = require('./probe_ee_ring_source.cjs');
const lane = (a,n)=>a.filter((_,i)=>i%3===n);
const hex = a=>a.map(n=>n.toString(16).toUpperCase()).join('');

function prepareProgram(calc) {
  // Physical Y's M3 page is program addresses 84..90 at the aligned phase.
  // The arithmetic preparation executes only 00..05, so this is inert data.
  calc.pressSequence(['БП','8','4','F','ВП','1','2','3','4','5','6','7',
                      'F','/-/','В/О']);
  assert.deepEqual(Array.from({length:7},(_,i)=>calc.readCommand(84+i)),[1,2,3,4,5,6,7]);
}

function isolatedAlternative(events,index,selector) {
  const before = events[index], chip = new MK61().ik1302;
  chip.reset();
  chip.r = before.r.slice(); chip.memory = before.m.slice(); chip.stack = before.st.slice();
  for (const key of ['s','s1','l','t','carry']) chip[key] = before[key];
  // EXPLICIT artificial change. It characterises the branch, not its reachability.
  chip.s1 = selector;
  const addresses = [], outputs = [];
  for (let command=0;command<3;command++) {
    addresses.push(chip.r[36]+16*chip.r[39]);
    const native = events[index+command], next = events[index+command+1], outgoing=[];
    for (let tick=0;tick<42;tick++) {
      chip.keyX=native.keyX; chip.keyY=native.keyY;
      // CC/BB do not change M, so these first three input packets also agree
      // with the native ring. No fabricated outgoing packet is fed back.
      chip.input=next.m[tick]; chip.tick(); outgoing.push(chip.output);
    }
    outputs.push(outgoing);
  }
  assert.deepEqual(addresses,[0xCC,0xBB,0xBC]);
  assert.deepEqual(lane(outputs[2],1),lane(before.r,1));
  assert.equal(chip.r[36]+16*chip.r[39],before.sp[0]);
  return {hostChangedS1:true,selector,addresses,writeSlot:events[index+2].slot,
          written:hex(lane(outputs[2],1)),returnIp:before.sp[0]};
}

function check(options={}) {
  const result = run('8.7654321E-71',{prepareProgram,...options});
  const e = result.tail, swaps=e.filter(x=>x.ip===0xC9);
  assert.equal(swaps.length,2);
  const first = swaps[0], second = swaps[1], read=e.find(x=>x.ip===0xC8);
  const ccIndex=e.findIndex(x=>x.command===second.command-2);
  const cc=e[ccIndex], helper=e.findLast(x=>x.ip===0x05 && x.command<cc.command);
  assert.equal(cc.ip,0xCC); assert.equal(cc.s1,9); assert.ok(helper);
  assert.equal(e[ccIndex+1].ip,0xCD);
  assert.deepEqual(lane(second.r,1),lane(first.m,2));
  assert.ok(lane(first.m,2).some(n=>n!==0),'nonzero old program page');
  const attempts=[10,15].map(s1=>isolatedAlternative(e,ccIndex,s1));
  assert.ok(attempts.every(a=>a.writeSlot===first.slot));
  assert.equal(first.slot,'Y'); assert.equal(read.slot,'W');
  assert.ok(attempts.every(a=>a.writeSlot!==read.slot),'counterfactual writes wrong M2 page');
  const source=lane(read.m,1), parked=lane(first.r,1);
  assert.notDeepEqual(parked,source,'C8 continuation does not preserve the full original page');
  assert.deepEqual(result.report.fullAfter,result.report.fullBefore);
  assert.ok(!e.some(x=>x.ip===0xBB || x.ip===0xBC));
  const report={options,sourceSlot:read.slot,programSlot:first.slot,
    source:hex(source),parked:hex(parked),oldProgram:hex(lane(first.m,2)),
    selectorAtCC:cc.s1,helperDistance:cc.command-helper.command,
    deltaReadToSwap:first.command-read.command,deltaBetweenSwaps:second.command-first.command,
    changedTetras:source.flatMap((v,i)=>v===parked[i]?[]:[{index:i,source:v,parked:parked[i]}]),
    attempts,nativeBBBC:false};
  console.log(JSON.stringify(report));
  return report;
}

if(require.main===module) {
  check();
  check({phaseOffset:1});
  check({phaseOffset:2,settleFrames:10});
  console.log('PASS: three keyboard fixtures and six explicitly artificial CC->BB->BC checks.');
  const input=new MK61();
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    input[name]=()=>{throw Error('Forbidden host setter: '+name);};
  input.pressSequence(['В/О','F','ВП','F','*','F','/-/','В/О']);
  aligned(input);
  assert.equal(input.readCommand(0),0x22);
  assert.ok(Object.values(fullMsPages(input)).every(word=>word.startsWith('00')));
  console.log('PASS: valid keyboard-prepared counterexample input: opcode 22 at step 00, '+
    'all Ms service bytes 00. A general K2 would have to create service byte 22.');
}
module.exports={check,isolatedAlternative};
