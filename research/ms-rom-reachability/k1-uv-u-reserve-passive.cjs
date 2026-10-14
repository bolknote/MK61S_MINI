#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {run:capture}=require('./k1-zero-capture-passive.cjs');
const run=options=>capture(options,'u-reserve');
if(require.main===module){
  const d=run(process.argv[2]?JSON.parse(process.argv[2]):{}),dir=fs.mkdtempSync('/private/tmp/k1-uv-u-reserve-'),
    out=path.join(dir,'native-proof.json');
  fs.writeFileSync(out,JSON.stringify(d),{flag:'wx'});
  console.log(JSON.stringify({output:out,sha256:crypto.createHash('sha256').update(fs.readFileSync(out)).digest('hex'),
    bytes:fs.statSync(out).size,metadata:d.metadata,activeWords:d.windows['cache-u'].length}));
}
module.exports={run};
