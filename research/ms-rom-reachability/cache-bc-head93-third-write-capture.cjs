#!/usr/bin/env node
'use strict';
// Export passive fresh native evidence, not executable/controller state.
// All three payloads entered/read by public keys; transient holders explicit.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {run}=require('./cache-bc-head93-third-write-native.cjs');
const files=['/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs','/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs',
  ...['ik1302_symbolic.py','analyze_gates.py','audit_ms_rom_control.py','k1-formatter-entry-audit.py'].map(n=>path.join(__dirname,n))];
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const frozen=Object.fromEntries(files.map(p=>[p,hash(p)]));
const v=run({proof:true});
for(const p of files)assert.equal(hash(p),frozen[p]);
const a=v.report.thirdAudit;
assert.ok(a.sourceReady&&a.stored&&a.firstHeldInR7&&a.secondHeldInP7&&a.thirdHeld);
assert.equal(a.firstDifference,null);assert.equal(a.thirdFirstDifference,null);
const data={schema:'mk61-third-write-passive-v1',metadata:{onlyPublicKeys:v.report.onlyPublicKeys,
  ALL5mirror:v.report.ALL5mirror,frozenSha256:frozen,
  boundary:'native P9 write; FIRST remains explicit R7 output, not independent Ms restoration/third read/full K1/K2'},
  cells:v.cells,report:v.report,
  windows:Object.fromEntries(Object.entries(v.windows).filter(([n])=>n.startsWith('packet-third-')||n==='packet-idle')),
  endpoints:Object.fromEntries(Object.entries(v.nativeEndpoints).filter(([n])=>n.startsWith('packet-third-'))),
  stages:v.exitStages.filter(s=>s.name.startsWith('packet-third-')||s.name==='packet-p7-first-output'||s.name==='packet-idle')};
const dir=fs.mkdtempSync('/private/tmp/mk61-third-write-'),out=path.join(dir,'native-proof.json');
fs.writeFileSync(out,JSON.stringify(data),{flag:'wx'});
console.log(JSON.stringify({output:out,sha256:hash(out),bytes:fs.statSync(out).size,audit:a,
  oldP10:v.report.packetAudit.firstDifference,boundary:data.metadata.boundary}));
