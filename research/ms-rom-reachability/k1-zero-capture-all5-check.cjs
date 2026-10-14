#!/usr/bin/env node
'use strict';
// Literal ALL5 entire native half-pair from its single real initial state.
// Every word checks protected emitted cells and the live original-P0 holder.
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
function run(file){
  const d=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(d.schema,'k1-zero-capture-passive-v1');
  for(const [f,h] of Object.entries(d.metadata.frozenSha256))
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'),h,f);
  const entry=d.endpoints['capture-start'],end=d.endpoints['capture-end'],core=m.make(entry);
  const observed=new Map(Object.values(d.windows).flat().map(v=>[v.word,v]));
  const fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
  const p=d.metadata.originalWords[0],v=d.metadata.originalWords[16];
  let words=0,checked=0,protectedCells=0,firstP0Write=null;
  for(const part of d.schedule)for(let j=0;j<part.count;j++){
    const native=observed.get(words),pins={...fixed,ik1302:part.key};
    if(native){m.compare(core,native.fullBefore,native.tagsBefore);assert.deepEqual(pins,m.pins(native));}
    const before=m.names.slice(2).map(chip=>({chip,m:core.chips[chip].m,ids:core.tags[chip].slice()}));
    const out=m.step(core,pins);
    for(const b of before)for(let n=0;n<42;n++){
      const c=d.cells[b.ids[n]],protectedCell=c.area==='program'||!Number.isInteger(c.field)||c.area==='Ms'||
        (c.area==='register'&&c.word!=='R0');
      if(protectedCell){assert.equal(out[b.chip][n],b.m[n],part.stage+'/'+words+'/'+b.chip+'/'+c.area+':'+c.word+'/'+c.field);protectedCells++;}
    }
    const r0=m.physical(core,d.cells,'register','R0');
    if(r0!==p){assert.equal(r0,v,'P0 may only change to original V');
      assert.equal(m.physical(core,d.cells,'stack','X1'),p,'original P0 remains whole in logical T');
      firstP0Write??={word:words,stage:part.stage};}
    if(native){assert.deepEqual(out.ik1302,native.emitted);m.compare(core,native.fullAfter,native.tagsAfter);checked++;}
    words++;
  }
  assert.equal(words,d.metadata.protocolWords);assert.equal(checked,observed.size);
  m.compare(core,end.fullBefore,end.tagsBefore);assert.ok(firstP0Write);
  assert.equal(m.physical(core,d.cells,'register','R0'),v);
  assert.equal(m.physical(core,d.cells,'stack','X1'),p);
  return{directALL5Words:words,nativeMatches:checked,protectedEmittedCells:protectedCells,firstP0Write,
    all5EndpointMatched:true,boundary:'whole native half-pair recalculated; actual source/program/service fields held. No reverse write/clean exit/full K1 or universal numeric/timing claim'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run};
