#!/usr/bin/env node
'use strict';
// NEW writer hypothesis: return the ready Y carrier to X while keeping the
// existing full-U LastX reserve, then enter the P0-carrier writer. No new reader
// is constructed. Passive endpoint -> detached ALL5 arrays only; no injected
// native calculator state and no invented bank/header repair.
const assert=require('node:assert/strict');
const {load}=require('./k1-zero-uv-reader-all5-check.cjs');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const {vector,reader,oldWord}=require('./k1-zero-t-passive-audit.cjs');
const {pins}=require('./k1-uv-reader-reverse-writer-plan.cjs');
function run(file){
  const d=load(file);assert.equal(d.schema,'k1-uv-u-reserve-passive-v1');
  const core=m.make(d.endpoints['reserve-end']),r=reader(d),initial=vector(core),
    fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[core.chips[n].keyX,core.chips[n].keyY]]));
  const state=()=>{const v=vector(core);return{
    visible:Object.fromEntries(['X','Y','Z','T','X1'].map(w=>[w,oldWord(r,v,d,w)])),
    banks:Array.from({length:15},(_,i)=>r.word(v,'register','R'+i.toString(16).toUpperCase()))
      .concat(['U','V','W','Q','P7','P8','P9','P10'].map(w=>r.word(v,'Ms',w)))};};
  assert.deepEqual(state().banks,d.metadata.originalWords);
  assert.equal(state().visible.Y,'0040F0000000');
  assert.equal(state().visible.X1,d.metadata.originalWords[15]);
  let words=0,firstProtectedChange=null,firstUReserveChange=null;
  const stages=[],paths=[];
  function act(stage,keys,frames=8){
    const start=state();
    for(const [count,key] of keys.flatMap(k=>{assert.ok(pins[k],k);return[[560,pins[k]],[560,[0,0]]];})
      .concat([[frames*560,[0,0]]]))for(let j=0;j<count;j++){
      const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
      if([0x9C,0xA3,0xE9,0xE7,0xEE,0xD4,0xD6].includes(ip)){
        const c=d.cells[core.tags.ik1302[[0xD4,0xD6].includes(ip)?21:22]];
        paths.push({stage,word:words,ip:ip.toString(16),owner:c.area+':'+c.word,
          a:p.r.filter((_,i)=>i<36&&i%3===0).reverse().map(v=>v.toString(16).toUpperCase()).join('')});
      }
      m.step(core,{...fixed,ik1302:key});
      const v=vector(core);
      for(let id=0;id<d.cells.length&&!firstProtectedChange;id++){
        const c=d.cells[id];if((c.area==='program'||String(c.field).startsWith('service'))&&v[id]!==initial[id])
          firstProtectedChange={stage,word:words,cell:c,before:initial[id],after:v[id]};
      }
      if(!firstUReserveChange&&oldWord(r,v,d,'X1')!==d.metadata.originalWords[15])
        firstUReserveChange={stage,word:words,value:oldWord(r,v,d,'X1')};
      words++;
    }
    stages.push({stage,start,end:state()});
  }
  // SWAP is the structural way to put the marker back on top. Abort rather
  // than silently storing U if the real ROM fails this stack precondition.
  act('return-carrier-to-X',['↔']);
  const afterSwap=state();
  let stopped=null;
  if(afterSwap.visible.X!=='0040F0000000')stopped='SWAP did not put m4 in X';
  else if(afterSwap.visible.X1!==d.metadata.originalWords[15])stopped='SWAP overwrote the only reserved U';
  else{
    act('store-carrier',['X→П','0']);
    act('push-carrier',['П→X','0']);
    act('first-synthetic-lastx',['F','В↑']);
    act('second-synthetic-lastx',['F','В↑']);
    const p=d.metadata.originalWords[0],v=d.metadata.originalWords[16],ready=state();
    if(ready.visible.X!==p||ready.visible.Y!==v||ready.visible.Z!=='0040F0000000'
       ||ready.visible.T!=='0040F0000000')stopped='Existing indirect-A writer source/marker precondition not created';
    else{
      act('indirect-p',['K','X→П',',']);
      act('p-to-t-marker',['П→X','0']);
      act('write-v',['↔']);
    }
  }
  const end=state(),stored=new Set([...end.banks,...Object.values(end.visible)]);
  return{words,stages,paths,firstProtectedChange,firstUReserveChange,stopped,
    bankChanges:end.banks.flatMap((w,i)=>w===d.metadata.originalWords[i]?[]:[{index:i,before:d.metadata.originalWords[i],after:w}]),
    absentOriginalsFromStoredWords:d.metadata.originalWords.filter(w=>!stored.has(w)),
    boundary:'detached proposed writer tail from an established U reserve; not native writer success or a full-state loss theorem'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run};
