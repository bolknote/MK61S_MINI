#!/usr/bin/env node
'use strict';
// A specific, structurally motivated counter alternative; not an exhaustive
// exclusion of other key protocols. All setup uses ordinary calculator keys.
const assert=require('node:assert/strict');
const {run}=require('./probe_a8_bank_keyboard.cjs');
const result=run({counter:'2.1111111'});
const events=result.traced.events;
const read=events.find(e=>e.ip===0xD6&&e.r[38]===2&&e.pc===0xF9);
assert.ok(read,'DD reading the loop counter really did prepare selector 2');
const store=events.find(e=>e.command>read.command&&e.ip===0xDD&&e.nextIp===0xD4);
assert.ok(store,'nonzero decremented loop counter takes the store branch');
const prefix=events.filter(e=>e.command>=store.command&&e.command<=store.command+5);
assert.deepEqual(prefix.map(e=>e.ip),[0xDD,0xD4,0x26,0x28,0x2A,0x63]);
assert.ok(prefix.every(e=>e.r[38]===2),'selector survives the store but not the later program fetch');
const fetch=events.find(e=>e.command>store.command&&e.ip===0xCD);
assert.ok(fetch&&fetch.r[38]===2&&fetch.nextIp===0xC9);
const after=events.find(e=>e.command===fetch.command+1);
assert.equal(after.ip,0xC9);assert.equal(after.r[38],8);
const gate=events.find(e=>e.command>fetch.command&&e.ip===0x60);
assert.ok(gate&&gate.r[38]===8&&gate.nextIp===0x08);
assert.equal(result.report.entries.length,0,'this alternative does not enter full-eight A8');
assert.deepEqual(result.report.after,result.report.before,'all Ms tetras remain unchanged');
console.log('PASS: counter 2.1111111 preserves selector 2 through DD/D4, but '+
  '26 -> 28 -> 2A -> 63 leads to a program fetch; CD replaces it with 8. No A8 entry.');
console.log('This rejects this key-only alternative, not all possible nonzero-counter preparations.');
