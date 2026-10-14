#!/usr/bin/env node
'use strict';
// Native original-ROM public-key reader corpus. No calculator state reads,
// reflection, setters, controller imports or ordinary register scratch.
const assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const candidate=require('./k1-zero-uv-retained-reader.cjs'),cap=require('./k1-bank-v-capture.cjs');
const {guarded,checkGuard}=require('./arbitrary-bank-pair-zero-capture-keyboard-check.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const files=['/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs','/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs',
  ...['ik1302_symbolic.py','analyze_gates.py','audit_ms_rom_control.py','k1-formatter-entry-audit.py'].map(n=>__dirname+'/'+n)];
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const cases=[...[0,1,2].map(phaseOffset=>({phaseOffset})),
  {incoming:'1.2345678E42',phaseOffset:0,values:['811','822','9.8765432E23','-4.44E12']},
  {incoming:'-1.234E-42',phaseOffset:1,values:['811','822','-9.8765432E-23','4.44E-12']},
  {incoming:'0',phaseOffset:2},
  {phaseOffset:0,values:['811','822','0','-1.2345678E99']},
  {phaseOffset:1,values:['811','822','-9.8765432E-99','0']},
  {phaseOffset:2,values:['811','822','9.8765432E99','-1.2345678E-99']},
  {phaseOffset:0,values:['811','822','-8.7654321E42','9.8765432E-42']}];
function main(){
  checkGuard();const frozen=Object.fromEntries(files.map(p=>[p,hash(p)])),results=[];
  for(const test of cases){
    const options={...candidate.base,...test},r=candidate.run(options),audit=candidate.check(r);
    const plain=cap.prepare(options),g=guarded(plain);
    candidate.operation(g.proxy,options);
    assert.equal(g.counts.keys,19);
    assert.equal(g.counts.extraFrames,120+options.phaseOffset);
    plain.runFrames(3);aligned(plain);
    assert.deepEqual(JSON.parse(JSON.stringify(plain)),JSON.parse(JSON.stringify(r.calc)),
      'fresh full native observer-free public-key mirror');
    results.push({options,P0:audit.P0,u:audit.u,v:audit.v,inputDistinctWords:audit.inputDistinctWords,
      all23BankWordsHeld:audit.all23BankWordsHeld,canonicalMarkerOnly:audit.canonicalMarkerOnly,
      keys:g.counts.keys,bodyFrames:2*g.counts.keys+g.counts.extraFrames});
    r.traced.events.length=r.traced.writes.length=0;
    console.log('PASS native U/V retained reader',JSON.stringify(results.at(-1)));
  }
  for(const [p,h] of Object.entries(frozen))assert.equal(hash(p),h,'frozen source changed');
  console.log(JSON.stringify({cases:results.length,frozenSixUnchanged:true,
    boundary:'U/V are copied to free visible Z/T, all original 23 bank words remain unchanged. No reverse writer, eight-pair K1 or universal timing/numeric proof.'}));
}
if(require.main===module)main();
module.exports={cases,main};
