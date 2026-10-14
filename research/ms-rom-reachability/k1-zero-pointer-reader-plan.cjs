#!/usr/bin/env node
'use strict';
// Source-directed indirect-reader hypotheses from the actual free P0=0.
// Record actual D6 owners: logical register names may be shifted by markers.
// No native state import, controller patch, or unconstrained key enumeration.
const assert=require('node:assert/strict');
const {run:prefix}=require('./k1-one-zero-t-reader-plan.cjs');
const {load,vector,reader,oldWord}=require('./k1-zero-t-passive-audit.cjs');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
function run(file){
  const d=load(file),r=reader(d),base=prefix(file),results=[];
  assert.equal(base.end.words[0],'000000000000');assert.equal(base.lost.length,0);
  // The C operands test a proposed modulo15 correction, not an enumeration.
  // Measured D6 owners refuted the assumed common shifted-register mapping:
  // RCL0 starts at actual R0, CALL0 at R5; C does not select free R0 safely.
  for(const [name,keys] of [['INDIRECT_RCL0',[[10,9],[8,9],[2,1]]],['INDIRECT_CALL0',[[10,9],[5,9],[2,1]]],
    ['INDIRECT_RCLC',[[10,9],[8,9],[9,8]]],['INDIRECT_CALLC',[[10,9],[5,9],[9,8]]]]){
    const core=structuredClone(base.core),initial=vector(core),fixed=Object.fromEntries(m.names.slice(2)
      .map(n=>[n,[core.chips[n].keyX,core.chips[n].keyY]]));
    const protectedIds=d.cells.flatMap((c,i)=>c.area==='program'||String(c.field).startsWith('service')?[i]:[]);
    let words=0,loss=null,protectedChange=null;const cacheReads=[],reads=[],ordinaryReads=[];
    for(const [count,key] of keys.flatMap(k=>[[560,k],[560,[0,0]]]).concat([[4480,[0,0]]]))for(let j=0;j<count;j++){
      const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39],owner=d.cells[core.tags.ik1302[22]];
      if(ip===0xC8)cacheReads.push({word:words,owner:owner.area+':'+owner.word,
        raw:m.physical(core,d.cells,owner.area,owner.word),R25:p.r[25],R31:p.r[31],R38:p.r[38],R26:p.r[26]});
      if(ip===0xD6&&ordinaryReads.length<8){const c=d.cells[core.tags.ik1302[21]];
        ordinaryReads.push({word:words,owner:c.area+':'+c.word,raw:m.physical(core,d.cells,c.area,c.word)});}
      if(ip===0xEE&&reads.length<12)reads.push({word:words,owner:owner.area+':'+owner.word,
        raw:m.physical(core,d.cells,owner.area,owner.word)});
      m.step(core,{...fixed,ik1302:key});const values=vector(core);
      const live=new Set([...r.groups.keys()].map(k=>{const at=k.indexOf(':');return r.word(values,k.slice(0,at),k.slice(at+1));}));
      const lost=d.metadata.originalWords.filter(w=>!live.has(w));if(lost.length&&!loss)loss={word:words,lost};
      for(const id of protectedIds)if(values[id]!==initial[id]&&!protectedChange)
        protectedChange={word:words,cell:d.cells[id],before:initial[id],after:values[id]};
      words++;
    }
    assert.equal(words,7840);const values=vector(core);
    results.push({name,words,cacheReads,reads,ordinaryReads,loss,protectedChange,P0:r.word(values,'register','R0'),
      visible:Object.fromEntries(['X','Y','Z','T'].map(w=>[w,oldWord(r,values,d,w)]))});
  }
  return{prefixWords:base.words,results,
    boundary:'four derived indirect-reader hypotheses in literal ALL5; not native new reader/full K1 or whole-ROM impossibility'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run};
