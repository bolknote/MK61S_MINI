#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
let words=0,windows=0;
for(const file of process.argv.slice(2)) {
  const d=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.ok(['mk61-two-word-reopen-passive-v1','mk61-third-write-passive-v1',
    'mk61-third-restore-passive-v1','mk61-third-restore-negative-passive-v1'].includes(d.schema),'unsupported passive trace schema');
  for(const [label,rows] of Object.entries(d.windows)) {
    if(!rows.length)continue;const core=model.make(rows[0]);
    assert.throws(()=>model.physical(core,d.cells,'missing-area','P9'),/missing physical field/);
    assert.match(model.physical(core,d.cells,'Ms','P9'),/^[0-9A-F]{12}$/);
    for(const v of rows) {
      model.compare(core,v.fullBefore,v.tagsBefore);
      const output=model.step(core,model.pins(v));
      assert.deepEqual(output.ik1302,v.emitted,label+'/'+v.word+' original output');
      model.compare(core,v.fullAfter,v.tagsAfter);words++;
    }
    windows++;
  }
}
console.log('PASS detached numeric ALL5',words,'native original words/',windows,
  'separate continuous windows; all working bits/ring/wires/phase/630 tags exact, no checkpoint repairs.');
