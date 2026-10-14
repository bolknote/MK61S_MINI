#!/usr/bin/env node
'use strict';
// Complete literal ALL5 recalculation. Native captures are passive comparisons,
// never transplanted into the calculator or used to repair the running arrays.
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
function load(file){
  const d=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.ok(['k1-zero-uv-reader-passive-v1','k1-uv-u-reserve-passive-v1','k1-uv-u-canonical-passive-v1'].includes(d.schema));
  for(const [f,h] of Object.entries(d.metadata.frozenSha256))
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'),h,f);
  return d;
}
function run(file,includeCore=false){
  const d=load(file),isReserve=d.schema==='k1-uv-u-reserve-passive-v1',
    isCanonical=d.schema==='k1-uv-u-canonical-passive-v1',
    entry=d.endpoints[isCanonical?'canonical-start':isReserve?'reserve-start':'reader-start'],
    end=d.endpoints[isCanonical?'canonical-end':isReserve?'reserve-end':'reader-end'],core=m.make(entry),
    observed=new Map(Object.values(d.windows).flat().map(v=>[v.word,v])),
    fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
  let words=0,checked=0,protectedCells=0;
  for(const part of d.schedule)for(let j=0;j<part.count;j++){
    const native=observed.get(words),pins={...fixed,ik1302:part.key};
    if(native){m.compare(core,native.fullBefore,native.tagsBefore);assert.deepEqual(pins,m.pins(native));}
    const before=m.names.slice(2).map(chip=>({chip,m:core.chips[chip].m,ids:core.tags[chip].slice()}));
    const out=m.step(core,pins);
    for(const b of before)for(let n=0;n<42;n++){
      const c=d.cells[b.ids[n]];
      if(c.area==='program'||!Number.isInteger(c.field)||c.area==='Ms'||c.area==='register'){
        assert.equal(out[b.chip][n],b.m[n],part.stage+'/'+words+'/'+b.chip+'/'+c.area+':'+c.word+'/'+c.field);
        protectedCells++;
      }
    }
    if(native){assert.deepEqual(out.ik1302,native.emitted);m.compare(core,native.fullAfter,native.tagsAfter);checked++;}
    words++;
  }
  assert.equal(words,d.metadata.protocolWords);assert.equal(checked,observed.size);
  m.compare(core,end.fullBefore,end.tagsBefore);
  const banks=Array.from({length:15},(_,i)=>m.physical(core,d.cells,'register','R'+i.toString(16).toUpperCase()))
    .concat(['U','V','W','Q','P7','P8','P9','P10'].map(w=>m.physical(core,d.cells,'Ms',w)));
  assert.deepEqual(banks,d.metadata.originalWords);
  const visible=Object.fromEntries(['X','Y','Z','T'].map(w=>[w,m.physical(core,d.cells,'stack',d.metadata.logicalMap[w])]));
  if(isCanonical){
    assert.equal(visible.X,d.metadata.originalWords[15]);
    assert.equal(m.physical(core,d.cells,'stack',d.metadata.logicalMap.X1),d.metadata.originalWords[15]);
    const words=['U','V','W','Q','P7','P8','P9','P10'].map(w=>m.physical(core,d.cells,'Ms',w))
      .concat(['X','Y','Z','T','X1'].map(w=>m.physical(core,d.cells,'stack',w)),
        ['aux0','aux1'].map(w=>m.physical(core,d.cells,'unclassified',w)));
    assert.deepEqual(words.flatMap((w,i)=>w[4]==='F'?[i]:[]),[13]);
  }else if(isReserve){
    assert.equal(visible.X,d.metadata.originalWords[15]);assert.equal(visible.Y,'0040F0000000');
    assert.equal(m.physical(core,d.cells,'stack',d.metadata.logicalMap.X1),d.metadata.originalWords[15]);
  }else assert.equal(visible.Z,d.metadata.originalWords[16]);
  if(!isCanonical)assert.equal(visible.T,d.metadata.originalWords[15]);
  const result={directALL5Words:words,nativeMatches:checked,protectedEmittedCells:protectedCells,
    all5EndpointMatched:true,phase:core.phase,visible,all23BankWordsHeld:true,
    boundary:isCanonical?'entire native U canonical LastX reserve/readback recalculated; no false marker, reverse writer, full K1 or universal timing/numeric claim':
      isReserve?'entire native U LastX reserve recalculated; false Y marker remains, no reverse writer, full K1 or universal timing/numeric claim':
      'entire native U/V reader recalculated; no reverse writer, full K1 or universal timing/numeric claim'};
  return includeCore?{...result,core,d}:result;
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={load,run};
