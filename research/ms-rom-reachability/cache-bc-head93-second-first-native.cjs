#!/usr/bin/env node
'use strict';
// First-slot continuation after the independently read physical P7 value.
// Fresh guarded originals/full mirrors; fixed public keys, no ROM/state edits.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357';
function run({proof=false,paced=false,p9=false,readFirst=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:readFirst?'p7-first-read':p9?'p7-first-p9':paced?'p7-first-paced':'p7-first-frontier'});
  const final=v.exitStages.at(-1);
  assert.equal(v.report.packetAudit.numberHeld,true);assert.equal(v.report.packetAudit.firstDifference,null);
  assert.equal(v.report.secondSlotAudit.numberHeld,true);assert.equal(v.report.secondSlotAudit.firstDifference,null);
  assert.equal(final.words['Ms:P7'],SECOND);assert.equal(final.words['Ms:P10'],FIRST);
  assert.equal(final.registers[6],SECOND);
  if(readFirst) {
    assert.equal(final.display,'12345678,');assert.equal(final.registers[7],FIRST);
    assert.deepEqual(final.markers,['Ms:P8']);
  } else assert.ok(!final.registers.includes(FIRST));
  return v;
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input')||process.argv.includes('--routes'),paced:process.argv.includes('--paced'),p9:process.argv.includes('--p9'),readFirst:process.argv.includes('--read-first')});
  const routes=process.argv.includes('--routes')?Object.fromEntries(
    ['packet-second-read-output',...Object.keys(v.windows).filter(n=>n.startsWith('packet-second-first'))]
      .map(label=>[label,v.windows[label].filter((x,i)=>i<5||[0x9E,0xEE,0xD6,0xD4,0xE7,0xA8,0xA3].includes(x.ip))
        .map(x=>({word:x.word,ip:x.ip.toString(16),owner:x.numericOwner,M1:x.ordinaryOwner,
          header:[x.fullBefore.ik1302.m[31],x.fullBefore.ik1302.m[34]],
          op:x.fullBefore.ik1302.r[30]+16*x.fullBefore.ik1302.r[33],
          mode:x.fullBefore.ik1302.r[2],R26:x.fullBefore.ik1302.r[26],
          source:x.fullBefore.ik1302.r.filter((_,j)=>j%3===0).slice(0,12).reverse().map(n=>n.toString(16)).join(''),
          next:x.fullAfter.ik1302.r[36]+16*x.fullAfter.ik1302.r[39]}))])):null;
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:routes||{
    stages:v.exitStages.filter(s=>s.name.startsWith('packet-second-first')||s.name==='packet-idle')
      .map(s=>({name:s.name,keys:s.keys,display:s.display,markers:s.markers,
        P7:s.words['Ms:P7'],P10:s.words['Ms:P10'],R6:s.registers[6],R7:s.registers[7]})),
    firstAudit:v.report.packetAudit,secondAudit:v.report.secondSlotAudit,
    onlyPublicKeys:true,ALL5mirror:true,boundary:process.argv.includes('--read-first')?
      'two stored Ms words recovered AFTER ordinary sources erased, both hidden words retained; normal work/repeat/bank still unproved':
      'new mixed first-reader frontier, not a complete two-word cycle'}));
}
module.exports={run};
