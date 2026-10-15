#!/usr/bin/env node
'use strict';
// Structural U-writer probe from the authentic ready writer endpoint.
// No manufactured processor state or ROM/key search: one derived Z-marker
// rotation, then LastX/ordinary unary operation to inspect E9(marker+2=U).
const assert=require('node:assert/strict');
const high=require('./k1-u-header-high-carrier.cjs');
const ready=require('./k1-high-carrier-ready-retry.cjs');
const {create}=require('./k1-writer-replay.cjs');
const stem=[['align-Z',[],2],['marker-to-Z',['F',',']]];
const variants={
  'unary-only':[['unary-with-Z',['K','-']]],
  'unary-key-compensated':[['align-extra-key',[],1],['unary-with-Z',['K','-']]],
  'lastx-unary':[['read-damaged-U',['F','В↑']],['unary-with-U',['K','-']]],
  'lastx-exp':[['read-damaged-U',['F','В↑']],['exp-with-U',['ВП']]],
  'lastx-roll':[['read-damaged-U',['F','В↑']],['ready-U-to-T',['F',',']]],
};
function run(file,variant='lastx-unary'){
  assert.ok(variants[variant]);const s=create(file);
  for(const a of [...high.maker,...high.writer,...ready.retry])s.advance(a,false);
  const start=s.state(),prefixWords=s.result().words;
  for(const a of [...stem,...variants[variant]])s.advance(a,true);
  const r=s.result();
  assert.equal(r.firstProtectedChange,null);
  assert.deepEqual(r.end.banks.slice(0,15),start.banks.slice(0,15));
  assert.deepEqual(r.end.banks.slice(19),start.banks.slice(19));
  const expected=start.banks.slice();
  if(variant==='lastx-unary')expected[15]='272'+expected[15].slice(3);
  if(variant==='lastx-exp')expected[17]='000000000000';
  if(variant!=='lastx-roll'){
    assert.deepEqual(r.end.banks,expected,'exact endpoint banks, not inferred non-loss');
    assert.equal(r.end.visible[variant.startsWith('unary-')?'Z':'T'],'0040F1200000',
      'the U-order reserve still exists');
  }
  return{variant,start,...r,newSuffixWords:r.words-prefixWords,
    stages:r.stages.slice(-stem.length-variants[variant].length),
    paths:r.paths.filter(p=>['9c','ee','e9','a3','e7'].includes(p.ip)),
    changes:r.changes.filter(c=>c.area==='Ms'),
    boundary:'authentic detached fixed-key suffix only; not native U restoration or complete K1'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],process.argv[3])));
module.exports={run,stem,variants};
