#!/usr/bin/env node
'use strict';
// Detached original-ROM five-chip replay of FIXED public-key writer actions.
// Evidence endpoints are inputs to plain arrays, never native state imports.
const assert=require('node:assert/strict');
const {load}=require('./k1-zero-uv-reader-all5-check.cjs');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
const {vector,reader,oldWord}=require('./k1-zero-t-passive-audit.cjs');
const pins={...require('./k1-u-header-marker-plan.cjs').pins,
  '6':[8,1],'9':[11,1],'*':[4,8]};
const MS=['U','V','W','Q','P7','P8','P9','P10'];
const raw=a=>a.filter((_,j)=>j<36&&j%3===0).reverse().map(n=>n.toString(16).toUpperCase()).join('');
function create(file,seed=null){
  const d=load(file);assert.equal(d.schema,'k1-zero-uv-reader-passive-v1');
  // A seed is an authentic detached model fork, never a calculator instance.
  const core=seed?structuredClone(seed):model.make(d.endpoints['reader-end']),r=reader(d),
    fixed=Object.fromEntries(model.names.slice(2).map(n=>[n,[core.chips[n].keyX,core.chips[n].keyY]]));
  let words=0,firstProtectedChange=null,protectedEmittedCells=0;
  const stages=[],changes=[],paths=[];
  function state(){const v=vector(core);return{phase:core.phase,
    visible:Object.fromEntries(['X','Y','Z','T','X1'].map(w=>[w,oldWord(r,v,d,w)])),
    banks:Array.from({length:15},(_,i)=>r.word(v,'register','R'+i.toString(16).toUpperCase())).concat(MS.map(w=>r.word(v,'Ms',w))),
    markers:['marker','control','X1','X','Y','Z','T',...MS].filter(w=>oldWord(r,v,d,w)[4]==='F')};}
  if(!seed)assert.deepEqual(state().banks,d.metadata.originalWords);
  function advance([stage,keys,frames=8],trace=false){
    const start=state();
    const schedule=keys.flatMap(k=>{assert.ok(pins[k],k);return[[560,pins[k]],[560,[0,0]]];}).concat([[frames*560,[0,0]]]);
    for(const [count,key] of schedule)for(let j=0;j<count;j++){
      const before=model.names.slice(2).map(chip=>({chip,m:core.chips[chip].m,ids:core.tags[chip].slice(),
        ip:core.chips[chip].r[36]+16*core.chips[chip].r[39],a:raw(core.chips[chip].r)}));
      if(trace){const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
        if([0x9C,0xEE,0xE3,0xE4,0xE5,0xE6,0xE7,0xE8,0xE9,0xA3,0xA8,0xD4,0xD6,0x47].includes(ip)){
          const c=d.cells[core.tags.ik1302[[0xD4,0xD6].includes(ip)?21:22]];
          paths.push({stage,word:words,ip:ip.toString(16),owner:c.area+':'+c.word,a:raw(p.r),s1:p.s1,r35:p.r[35]});
        }
      }
      const out=model.step(core,{...fixed,ik1302:key});
      for(const b of before)for(let n=0;n<42;n++){
        const c=d.cells[b.ids[n]],protectedCell=c.area==='program'||String(c.field).startsWith('service');
        if(protectedCell)protectedEmittedCells++;
        if(out[b.chip][n]!==b.m[n]){
          const change={stage,word:words,chip:b.chip,ip:b.ip.toString(16),area:c.area,owner:c.word,
            field:c.field,before:b.m[n],after:out[b.chip][n],a:b.a};
          if(protectedCell&&!firstProtectedChange)firstProtectedChange=change;
          if(trace&&(c.area==='Ms'||c.area==='register'||c.field===7))changes.push(change);
        }
      }
      words++;
    }
    stages.push({stage,start,end:state()});return stages.at(-1);
  }
  function result(){const end=state(),stored=new Set([...end.banks,...Object.values(end.visible)]);
    return{words,protectedEmittedCells,stages,changes,paths,firstProtectedChange,end,
      bankChanges:end.banks.flatMap((w,i)=>w===d.metadata.originalWords[i]?[]:[{index:i,before:d.metadata.originalWords[i],after:w}]),
      absentOriginalsFromStoredWords:d.metadata.originalWords.filter(w=>!stored.has(w)),
      boundary:'detached fixed-key writer hypothesis; absence from stored words alone is not irreversible full-state loss'};}
  return{core,d,state,advance,result};
}
module.exports={create,pins,MS};
