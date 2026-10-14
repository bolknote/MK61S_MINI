#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const {run}=require('./cache-bc-head93-third-restore-native.cjs');
const files=['/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs','/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs',
  ...['ik1302_symbolic.py','analyze_gates.py','audit_ms_rom_control.py','k1-formatter-entry-audit.py'].map(n=>path.join(__dirname,n))];
const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const negativeCX=process.argv.includes('--negative-cx');
const frozen=Object.fromEntries(files.map(p=>[p,hash(p)])),v=run({proof:true,negativeCX});
for(const p of files)assert.equal(hash(p),frozen[p]);
const selected=n=>n==='packet-third-write-P9'||n.startsWith('packet-third-restore-')||n==='packet-idle';
const data={schema:negativeCX?'mk61-third-restore-negative-passive-v1':'mk61-third-restore-passive-v1',metadata:{onlyPublicKeys:v.report.onlyPublicKeys,negativeCX,
  ALL5mirror:v.report.ALL5mirror,frozenSha256:frozen,boundary:v.restoration.audit.boundary},
  cells:v.cells,report:{thirdAudit:v.report.thirdAudit,thirdRestoreAudit:v.report.thirdRestoreAudit,
    oldFixedP10:v.report.packetAudit},stages:v.restoration.stages,
  windows:Object.fromEntries(Object.entries(v.windows).filter(([n])=>selected(n))),
  endpoints:Object.fromEntries(Object.entries(v.nativeEndpoints).filter(([n])=>selected(n)))};
const dir=fs.mkdtempSync('/private/tmp/mk61-third-restore-'),out=path.join(dir,'native-proof.json');
fs.writeFileSync(out,JSON.stringify(data),{flag:'wx'});
const proof=require('./cache-bc-head93-third-restore-all5.cjs').run(out,out);
console.log(JSON.stringify({output:out,sha256:hash(out),bytes:fs.statSync(out).size,
  audit:v.restoration.audit,proof,boundary:data.metadata.boundary}));
