#!/usr/bin/env node
'use strict';
// Two fixed tail commands from the calculated Y-marker prefix. No native
// state import and no control edit. All early prefix words are recalculated.
const {load,vector,reader,oldWord}=require('./k1-zero-t-passive-audit.cjs');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
function run(file){
  const d=load(file),entry=d.endpoints['capture-start'],core=m.make(entry),r=reader(d);
  const fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
  let words=0;const events=[];
  const execute=(count,key,stage)=>{for(let j=0;j<count;j++){
    const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
    if(stage.startsWith('tail')&&[0x9C,0xD4,0xEE,0xE7,0xA8,0xA3,0x46].includes(ip)){
      const c=d.cells[core.tags.ik1302[ip===0xD4?21:22]];
      events.push({word:words,stage,ip,owner:c.area+':'+c.word,
        raw:m.physical(core,d.cells,c.area,c.word)});
    }
    m.step(core,{...fixed,ik1302:key});words++;
  }};
  for(const segment of d.schedule){if(segment.stage==='zero-capture-zero-1')break;
    execute(segment.count,segment.key,'prefix');}
  const view=()=>{const v=vector(core);return{
    visible:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,oldWord(r,v,d,n)])),
    words:d.metadata.originalWords.map((_,i)=>i<15?r.word(v,'register','R'+i.toString(16).toUpperCase()):
      r.word(v,'Ms',['U','V','W','Q','P7','P8','P9','P10'][i-15]))};};
  const inlet=view();
  for(const [stage,keys] of [['tail-save-u',[[6,9],[2,1]]],['tail-read-t',[[11,9],[11,8]]]]){
    for(const key of keys){execute(560,key,stage);execute(560,[0,0],stage);}
    execute(4480,[0,0],stage);
  }
  const end=view(),v=vector(core),live=[...r.groups.keys()].map(k=>{const at=k.indexOf(':');return r.word(v,k.slice(0,at),k.slice(at+1));});
  return{words,inlet,end,events,lost:d.metadata.originalWords.filter(w=>!live.includes(w)),core,
    boundary:'literal ALL5 two-command Y-marker hypothesis; not native reverse writer or full K1'};
}
if(require.main===module){const {core,...report}=run(process.argv[2]);console.log(JSON.stringify(report));}
module.exports={run};
