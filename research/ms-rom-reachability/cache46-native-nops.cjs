#!/usr/bin/env node
'use strict';
// Original-ROM 55/56 candidates: their native NOP bodies occur after EE.
const assert=require('node:assert/strict');
const {capture}=require('./cache46-native-lifecycle.cjs');
const positions=[0,3,9,12,18,21];
const cases=[
  {name:'K1_original55',keys:['K','1'],body:[0x1F,0x15,0x0F,0xD3]},
  {name:'K2_original56',keys:['K','2'],body:[0x1F,0x16,0x3F,0xD3]},
];

function check(c) {
  const result=capture(c),events=result.events;
  const ee=events.findIndex(e=>e.ip===0xEE),body=events.findIndex(e=>e.ip===0x1F);
  assert.ok(ee>=0&&body>ee,'the first EE precedes the original NOP body');
  assert.deepEqual(events.slice(body,body+4).map(e=>e.ip),c.body);
  const payload=positions.map(n=>result.initial.ik1302.r[n]);
  assert.deepEqual(positions.map(n=>events[ee].r[n]),payload,'raw cache reaches the first EE');
  assert.notDeepEqual(positions.map(n=>events[ee+1].r[n]),payload,'EE replaces the original raw cache');
  assert.notDeepEqual(positions.map(n=>events[body].r[n]),payload,'NOP receives ordinary X rather than raw cache');
  for(let n=0;n<36;n+=3) assert.equal(events[ee+1].r[n],events[ee].m[n+1]);
  const report={name:c.name,keys:c.keys,firstEE:events[ee].command,NOPBodyStart:events[body].command,
    body:c.body.map(n=>n.toString(16).toUpperCase()),
    cacheBeforeEE:positions.map(n=>events[ee].r[n]),
    cacheAfterEE:positions.map(n=>events[ee+1].r[n]),rawCacheHeldBeforeNOP:false,
    noCachePreservingModeReset:true,scope:'these two fixed original-ROM key protocols only',partialK2:false};
  console.log(JSON.stringify(report));
  return {result,report};
}
if(require.main===module) {
  for(const c of cases) check(c);
  console.log('PASS: two native original-ROM 55/56 bodies; both follow destructive EE before any mode reset.');
}
module.exports={check,cases};
