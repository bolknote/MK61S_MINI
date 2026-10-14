#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const p=require('./probe_ms_lower_guarded_exchange.cjs');
const base=require('./check_ms_lower_exchange.cjs');
const {checkGuard}=require('./check_ms_u_guard.cjs');
const {oldCounter}=require('./check_ms_lower_secondary_exchange.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function check(r,o={}) {
  const guard=checkGuard(r,{prefix:'prepare-q/',next:'read-last/exchange-wq/clear-before'});
  const result=base.check(r,{...o,secondaryW:true,uGuard:true});
  return {...result,guard:guard.map(e=>e.slot)};
}
const mixed={bank:['-8.7654321E-63','-1E-99','-1.2345678E-42','9.8765432E99'],
  values:['-7.654321E-87','-1.2345678E-42','-9.8765432E99','-2.3456789E-98'],
  fullUpper:['-3.2109876E-19','-4.3210987E-31','1.2345678E-42','-9.8765432E17']};
const cases=[{},...[0,1,2].map(phaseOffset=>({...oldCounter,phaseOffset})),
  ...[0,1,2].map(phaseOffset=>({...mixed,phaseOffset})),
  {...mixed,phaseOffset:2,settleFrames:12,markerFrames:8},
  {bank:['0','0','0','0'],values:['0','0','0','0']}];
function controls(expected,o={}) {
  assert.match(expected??'',/^[0-9a-f]{64}$/);
  const plain=p.prepare(o),ms=fullMsPages(plain),regs=registers(plain),prg=program(plain);
  p.finish(plain,o);plain.runFrames(3);aligned(plain);
  assert.equal(digest(plain),expected);console.log('PASS observed/unobserved full core:',expected);
  const back=p.runPrepared(plain,{...o,phaseOffset:1});console.log('PASS reverse paths:',JSON.stringify(check(back)));
  assert.deepEqual(back.after,ms);assert.deepEqual(back.afterRegisters.slice(0,9),regs.slice(0,9));assert.deepEqual(back.afterProgram,prg);
  base.release(back);console.log('PASS repeat without reset/preparation restores both banks, upper Ms, P4..P8 and program; scratch excluded.');
}
function main() {
  if(process.env.MS_GUARDED_MIXED_CONTROLS_ONLY==='1')return controls(process.env.MS_GUARDED_EXPECTED_DIGEST,{...mixed,phaseOffset:2,settleFrames:12,markerFrames:8});
  if(process.env.MS_GUARDED_CONTROLS_ONLY==='1')return controls(process.env.MS_GUARDED_EXPECTED_DIGEST);
  const from=Number(process.env.MS_GUARDED_FROM??0),count=Number(process.env.MS_GUARDED_CASES??cases.length);
  let firstDigest;const wOverlap=new Set(),qOverlap=new Set(),clearRounds=new Set();
  for(const o of cases.slice(from,from+count)) {
    const r=p.run(o),d=digest(r.calc);if(from===0)firstDigest??=d;
    const path=check(r);wOverlap.add(path.wOverlap);qOverlap.add(path.overlap);
    path.guard.forEach((slot,i)=>{if(slot==='U')clearRounds.add(i);});
    console.log('PASS guarded lower exchange:',JSON.stringify(o),JSON.stringify(path));console.log('OBSERVED_DIGEST',d);base.release(r);
  }
  console.log('COVERAGE',JSON.stringify({from,count:Math.min(count,cases.length-from),wOverlap:[...wOverlap],qOverlap:[...qOverlap],clearRounds:[...clearRounds],firstDigest}));
  if(from||count<cases.length)return;controls(firstDigest);
  console.log('LIMIT: tested lower four-pair exchange and fixed frame profiles; not full K1, arbitrary electrical timing, or restored scratch registers.');
}
if(require.main===module)main();
module.exports={check,cases,mixed,controls,release:base.release};
