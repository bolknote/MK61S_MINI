#!/usr/bin/env node
'use strict';
// Fixed parser hypothesis: EXP then NOP from the actual zero-capture inlet.
// Try the documented marker suffix without invoking NOT/its destructive
// arithmetic request. No imported native state, controller edits or key sweep.
const assert=require('node:assert/strict');
const {load,vector,reader,oldWord}=require('./k1-zero-t-passive-audit.cjs');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
function run(file,{tail='NOP'}={}){
  const d=load(file),entry=d.endpoints['capture-end'],core=m.make(entry),r=reader(d),initial=vector(core);
  const fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
  const protectedIds=d.cells.flatMap((c,i)=>c.area==='program'||String(c.field).startsWith('service')?[i]:[]);
  const groups=[...r.groups.keys()];let words=0,loss=null,protectedChange=null;const stages=[],events=[];
  const tails={NOP:[[10,9],[2,1]],STORE0:[[6,9],[2,1]],NOT:[[10,9],[3,8]]};
  assert.ok(tails[tail]);
  for(const [stage,keys] of [['EXP',[[9,8]]],[tail,tails[tail]]]){
    const segments=keys.flatMap(key=>[[560,key],[560,[0,0]]]).concat([[4480,[0,0]]]);
    for(const [count,key] of segments)for(let j=0;j<count;j++){
      const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
      if([0xEE,0xE7,0xA8,0xA3,0xC8].includes(ip)&&events.length<30)
        events.push({word:words,stage,ip,owner:d.cells[core.tags.ik1302[22]]});
      m.step(core,{...fixed,ik1302:key});const values=vector(core);
      const live=new Set(groups.map(k=>{const at=k.indexOf(':');return r.word(values,k.slice(0,at),k.slice(at+1));}));
      const lost=d.metadata.originalWords.filter(w=>!live.has(w));
      if(lost.length&&!loss)loss={word:words,stage,lost};
      for(const id of protectedIds)if(values[id]!==initial[id]&&!protectedChange)
        protectedChange={word:words,stage,cell:d.cells[id],before:initial[id],after:values[id]};
      words++;
    }
    const values=vector(core);
    stages.push({stage,visible:Object.fromEntries(['X1','X','Y','Z','T'].map(w=>[w,oldWord(r,values,d,w)])),
      P0:r.word(values,'register','R0'),packet:{R2:core.chips.ik1302.r[2],R25:core.chips.ik1302.r[25],
        R31:core.chips.ik1302.r[31],R38:core.chips.ik1302.r[38],R26:core.chips.ik1302.r[26]},
      markers:['marker','control','X1','X','Y','Z','T','U','V','W','Q','P7','P8','P9','P10']
        .filter(w=>oldWord(r,values,d,w)[4]==='F')});
  }
  assert.equal(words,12320);
  return{tail,words,loss,protectedChange,stages,events,
    boundary:'two fixed parser keys in detached ALL5 from native inlet; not native new marker or full K1'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],{tail:process.argv[3]||'NOP'})));
module.exports={run};
