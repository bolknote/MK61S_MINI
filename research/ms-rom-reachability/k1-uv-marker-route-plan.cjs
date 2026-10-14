#!/usr/bin/env node
'use strict';
// Move the sole false marker in m/p/v/u, rather than duplicating m and
// dropping the U reserve. Each continuation is derived from stack geometry.
// Detached ALL5 arrays only; no calculator state/ROM/controller writes.
const assert=require('node:assert/strict');
const {run:prefix}=require('./k1-zero-uv-reader-all5-check.cjs');
const {recipes,writerTail,pins}=require('./k1-uv-reader-reverse-writer-plan.cjs');
const {vector,reader,oldWord}=require('./k1-zero-t-passive-audit.cjs');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
function run(file){
  const baseline=prefix(file,true),{d}=baseline,r=reader(d),core=baseline.core,
    fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[core.chips[n].keyX,core.chips[n].keyY]]));
  assert.equal(d.schema,'k1-zero-uv-reader-passive-v1');
  const describe=core=>{const v=vector(core);return{visible:Object.fromEntries(['X','Y','Z','T','X1'].map(w=>[w,oldWord(r,v,d,w)])),
    banks:Array.from({length:15},(_,i)=>r.word(v,'register','R'+i.toString(16).toUpperCase()))
      .concat(['U','V','W','Q','P7','P8','P9','P10'].map(w=>r.word(v,'Ms',w))),
    falseMarkers:['X','Y','Z','T','X1','U','V','W','Q','P7','P8','P9','P10']
      .filter(w=>oldWord(r,v,d,w)[4]==='F')};};
  const advance=(core,actions)=>{
    let words=0,firstProtectedChange=null;const initial=vector(core),paths=[],stages=[],gateCounts={};
    for(const [stage,keys,frames=8] of actions){
      const start=describe(core);
      for(const [count,key] of keys.flatMap(k=>{assert.ok(pins[k],k);return[[560,pins[k]],[560,[0,0]]];})
        .concat([[560*frames,[0,0]]]))for(let j=0;j<count;j++){
        const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
        if(ip===0x9C){const c=d.cells[core.tags.ik1302[22]],key=stage+'/'+c.area+':'+c.word;
          gateCounts[key]=(gateCounts[key]??0)+1;}
        if([0xEE,0xE9,0xE7,0xA3,0xD4,0xD6].includes(ip)){
          const c=d.cells[core.tags.ik1302[[0xD4,0xD6].includes(ip)?21:22]];
          paths.push({stage,word:words,ip:ip.toString(16),owner:c.area+':'+c.word,
            raw:m.physical(core,d.cells,c.area,c.word),
            a:p.r.filter((_,i)=>i<36&&i%3===0).reverse().map(n=>n.toString(16).toUpperCase()).join('')});
        }
        m.step(core,{...fixed,ik1302:key});const now=vector(core);
        for(let id=0;id<d.cells.length&&!firstProtectedChange;id++){
          const c=d.cells[id];if((c.area==='program'||String(c.field).startsWith('service'))&&now[id]!==initial[id])
            firstProtectedChange={stage,word:words,cell:c,before:initial[id],after:now[id]};
        }
        words++;
      }
      stages.push({stage,start,end:describe(core)});
    }
    return{words,paths,gateCounts,stages,firstProtectedChange,end:describe(core)};
  };
  const stem=advance(core,[...recipes['payload-tail'],...writerTail.slice(0,8)]);
  assert.deepEqual(stem.end.banks,d.metadata.originalWords);
  assert.deepEqual(stem.end.visible,{X:'0040F0000000',Y:d.metadata.originalWords[0],
    Z:d.metadata.originalWords[16],T:d.metadata.originalWords[15],X1:'000000000000'});
  assert.equal(stem.firstProtectedChange,null);
  const routes=[];
  for(const [name,actions] of [
    ['single-marker-to-T',[['marker-to-T',['F',',']]]],
    ['single-marker-to-Y',[['marker-to-Y',['↔']]]],
    ['Y-lastx',[['marker-to-Y',['↔']],['reserve-lastx',['F','В↑']]]],
    ['Y-save-u-lastx',[['marker-to-Y',['↔']],['save-u-lastx',['K','-']]]],
    ['U-reserve-two-swap',[['marker-to-Y',['↔']],['save-u-lastx',['K','-']],
      ['recall-p',['П→X','0']],['capture-v',['X→П','0']],['push-v',['П→X','0']],
      ['prepare-request',['↔']],['accepted-request',['↔']]]],
    ['U-reserve-three-swap',[['marker-to-Y',['↔']],['save-u-lastx',['K','-']],
      ['recall-p',['П→X','0']],['capture-v',['X→П','0']],['push-v',['П→X','0']],
      ['prepare-request',['↔']],['accepted-request',['↔']],['write-p',['↔']]]],
    // Exact selected-integer identity, not a universal decimal-word transport.
    // Two requests restore W/Q; p+v-v can make p the real X without SWAP's
    // late old-X formatter undoing the visible exchange.
    ['U-reserve-integer-identity',[['marker-to-Y',['↔']],['save-u-lastx',['K','-']],
      ['recall-p',['П→X','0']],['capture-v',['X→П','0']],['push-v',['П→X','0']],
      ['prepare-request',['↔']],['restore-WQ',['↔']],['sum-pv',['+']],
      ['recall-v',['П→X','0']],['recover-p',['-']],['push-p-marker',['В↑']],['write-p',['↔']]]],
    ['Y-recall-p',[['marker-to-Y',['↔']],['recall-p',['П→X','0']]]],
    ['Y-recall-p-store0',[['marker-to-Y',['↔']],['recall-p',['П→X','0']],['save-pair',['X→П','0']]]]
  ]){
    const branch=structuredClone(core),out=advance(branch,actions);
    const values=vector(branch),live=new Set([...r.groups.keys()].map(k=>{const at=k.indexOf(':');
      return r.word(values,k.slice(0,at),k.slice(at+1));}));
    routes.push({name,...out,absentOriginalsFromStoredWords:d.metadata.originalWords.filter(w=>!live.has(w)),
      bankChanges:out.end.banks.flatMap((v,i)=>v!==d.metadata.originalWords[i]?
      [{index:i,before:d.metadata.originalWords[i],after:v}]:[])});
  }
  return{prefixWords:baseline.directALL5Words,stem,routes,
    boundary:'geometrically derived marker/request routes in detached ALL5; not a native writer, full K1 or impossibility proof'};
}
if(require.main===module){const out=run(process.argv[2]);console.log(JSON.stringify({...out,
  stem:{words:out.stem.words,end:out.stem.end,firstProtectedChange:out.stem.firstProtectedChange}}));}
module.exports={run};
