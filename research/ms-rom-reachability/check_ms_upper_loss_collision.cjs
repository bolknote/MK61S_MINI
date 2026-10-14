#!/usr/bin/env node
'use strict';
// Two different native input numbers converge to exactly the same emulator
// state after the failed exit. A partial IK1303 mantissa is not a full backup.
const assert=require('node:assert/strict');
const p=require('./probe_ms_upper_swap.cjs');
const {digest}=require('./check_c8_keyboard.cjs');
const {createHash}=require('node:crypto');
// JSON includes every serializable own data field, including chip command,
// syncAddress, flags, display, ROMs, all memories and all internal registers.
// The identical class methods and restored observer functions are not state.
const state=calc=>JSON.parse(JSON.stringify(calc));
function main() {
  const options={phaseOffset:2,stress:true,afterKeys:[['Сx']]};
  const a=p.run({...options,upperValues:['111','222','333','444']});
  const b=p.run({...options,upperValues:['1.11','222','333','444']});
  assert.equal(a.before.P8,'00002011100000');assert.equal(b.before.P8,'00000011100000');
  assert.deepEqual({...a.before,P8:b.before.P8},b.before,'only P8 differs among the initial Ms words');
  assert.deepEqual(a.beforeRegisters,b.beforeRegisters);assert.deepEqual(a.beforeProgram,b.beforeProgram);
  for(const r of [a,b]) {
    const es=r.traced.events,at=es.findIndex(e=>e.stage==='upper-after-0'&&e.ip===0xE7&&e.slot==='P7');
    assert.ok(at>=0);assert.equal(es[at].raw,r.before.P8.slice(2));assert.equal(es[at+1].ip,0x47);
    assert.deepEqual(r.traced.primitives,[]);assert.ok(es.every(e=>e.ip!==0xC9));
    assert.deepEqual(r.afterProgram,r.beforeProgram);assert.equal(r.after.P7,'00000000000000');
  }
  assert.deepEqual(a.after,b.after);assert.deepEqual(a.afterRegisters,b.afterRegisters);
  const sa=state(a.calc),sb=state(b.calc);
  assert.deepEqual(sa,sb,'not just a display/hash match: every serialized state field is identical');
  assert.equal(digest(a.calc),digest(b.calc));
  console.log('PASS: initial Ms P8=111 and P8=1.11 produce identical complete emulator data states after swap + phase-2 Cx.');
  console.log('Core-state SHA-256:',digest(a.calc));
  console.log('All serialized fields SHA-256:',createHash('sha256').update(JSON.stringify(sa)).digest('hex'));
  console.log('Therefore no common deterministic keyboard continuation can recover both original numbers from these final states.');
  console.log('This excludes recovery AFTER this lossy exit, not an earlier copy, another exit or full K1 by another protocol.');
}
if(require.main===module)main();
module.exports={state};
