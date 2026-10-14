#!/usr/bin/env node
'use strict';
// Generate a small PASSIVE native-evidence artifact for detached ROM work.
// Public fresh guarded reference+mirror, then read-only export. No device
// state import and no generated source file. New exclusive temp directory.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const p7Both=process.argv.includes('--p7-both');
const p7Read=p7Both||process.argv.includes('--p7-read');
const {run}=require(p7Both?'./cache-bc-head93-second-p7-both-native.cjs':p7Read?'./cache-bc-head93-second-p7-read-native.cjs':'./cache-bc-head93-second-reopen-swap-native.cjs');
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const frozen=['/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs',
  '/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs',
  ...['ik1302_symbolic.py','analyze_gates.py','audit_ms_rom_control.py','k1-formatter-entry-audit.py']
    .map(n=>path.join(__dirname,n))];
const sources=Object.fromEntries(frozen.map(p=>[p,hash(p)]));
const data=run({proof:true});
for(const p of frozen)if(hash(p)!==sources[p])throw Error('frozen source changed during capture: '+p);
const result={schema:'mk61-two-word-reopen-passive-v1',
  metadata:{profile:p7Both?'p7-normal-retain-both':p7Read?'p7-normal-retain-read':'p8-reopen-swap',frozenSha256:sources,
    onlyPublicKeys:data.report.onlyPublicKeys,ALL5mirror:data.report.ALL5mirror,
    boundary:p7Both?'measured native BOTH reads after normal math; no third-word/repeat claim':p7Read?'measured native P7 read after normal math; no P10 re-read/repeat claim':'measured FAILED native SWAP; model hypotheses are not imported into the device'},
  cells:data.cells,windows:Object.fromEntries(['packet-reopen-control-front3',
    'packet-reopen-control-swap','packet-second-first-V','packet-normal-clear',
    'packet-normal-aux0','packet-normal-Y','packet-normal-X1','packet-normal-relocate',
    'packet-normal-preclear4','packet-p7-read-output',...Object.keys(data.windows).filter(n=>n.startsWith('packet-p7-first-')),'packet-idle']
    .filter(n=>data.windows[n]).map(n=>[n,data.windows[n]])),
  endpoints:Object.fromEntries(['packet-second-first-output','packet-normal-clear',
    'packet-normal-erase7','packet-normal-aux0','packet-normal-port5','packet-normal-Y',
    'packet-normal-X1','packet-normal-preclear4','packet-p7-read-output','packet-p7-first-output',
    'packet-reopen-control-front3','packet-reopen-control-swap'].filter(n=>data.nativeEndpoints[n])
    .map(n=>[n,data.nativeEndpoints[n]])),
  stages:Object.fromEntries(['packet-second-first-output','packet-normal-clear',
    'packet-normal-erase7','packet-normal-aux0','packet-normal-port5','packet-normal-Y',
    'packet-normal-X1','packet-normal-preclear4','packet-p7-read-output','packet-p7-first-output',
    'packet-reopen-control-front3','packet-reopen-control-swap','packet-idle']
    .filter(n=>data.exitStages.some(s=>s.name===n))
    .map(n=>[n,data.exitStages.find(s=>s.name===n)])),
  audits:{first:data.report.packetAudit,second:data.report.secondRelocationAudit}};
const dir=fs.mkdtempSync('/private/tmp/mk61-reopen-evidence-');
const output=path.join(dir,'native-proof.json');
fs.writeFileSync(output,JSON.stringify(result),{flag:'wx'});
console.log(JSON.stringify({output,sha256:hash(output),bytes:fs.statSync(output).size,
  words:Object.fromEntries(Object.entries(result.windows).map(([n,v])=>[n,v.length])),
  boundary:result.metadata.boundary}));
