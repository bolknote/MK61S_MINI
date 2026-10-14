#!/usr/bin/env node
'use strict';
// Derive marker payload from U with public operations rather than injecting
// fixture digits. lg/integer-part is ONLY a selected positive-order prototype:
// it is not an exact universal exponent extractor (zero and rounding matter).
const assert=require('node:assert/strict');
const {load}=require('./k1-zero-uv-reader-all5-check.cjs');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const {vector,reader,oldWord}=require('./k1-zero-t-passive-audit.cjs');
const actions=[
  ['source-roll-0',['F',',']],['source-roll-1',['F',',']],['source-p0',['П→X','0']],
  ['source-roll-2',['F',',']],['source-roll-3',['F',',']],
  ['abs-u',['K','4']],['lg-u',['F','2']],['prototype-order',['K','7']],['drop-zero',['+']],
  ['scale-constant',[...'10000000']],['scale-order',['/']],['mask-constant',['1',',','8']],['mask-order',['+']],
  ['copy-mask',['В↑']],['or-constant',['1',',','7']],['or-mask',['K','/-/']],
  ['save-mask',['X→П','0']],['drop-or-result',['Сx','+']],['drop-or-operand',['Сx','+']],
  ['restore-mask',['П→X','0']],['marker-fraction',['K','8']],['marker-exponent',['ВП','5']],
  ['save-carrier',['X→П','0']],['push-carrier',['П→X','0']],
  ['lastx-v',['F','В↑']],['lastx-p',['F','В↑']],['indirect-p',['K','X→П',',']],
  ['p-to-t-marker',['П→X','0']],['write-v',['↔']]
];
const pins={...require('./k1-uv-reader-reverse-writer-plan.cjs').pins,
  '1':[3,1],'2':[4,1],'3':[5,1],'5':[7,1],'7':[9,1],'8':[10,1],'/':[5,8],'/-/':[8,8]};
function run(file,options={}){
  const d=load(file);assert.equal(d.schema,'k1-zero-uv-reader-passive-v1');
  const core=m.make(d.endpoints['reader-end']),r=reader(d),initial=vector(core),
    fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[core.chips[n].keyX,core.chips[n].keyY]]));
  const describe=()=>{const v=vector(core);return{
    visible:Object.fromEntries(['X','Y','Z','T','X1'].map(w=>[w,oldWord(r,v,d,w)])),
    banks:Array.from({length:15},(_,i)=>r.word(v,'register','R'+i.toString(16).toUpperCase()))
      .concat(['U','V','W','Q','P7','P8','P9','P10'].map(w=>r.word(v,'Ms',w)))};};
  assert.deepEqual(describe().banks,d.metadata.originalWords);
  const stages=[],paths=[];let words=0,firstProtectedChange=null,firstOtherBankChange=null,protectedEmittedCells=0;
  const selected=(options.stop?actions.slice(0,actions.findIndex(a=>a[0]===options.stop)+1):actions)
    .concat(options.continuation??[]);
  assert.ok(selected.length,'unknown stop stage');
  for(const [stage,keys] of selected){
    const start=describe(),phaseBefore=core.phase;
    for(const [count,key] of keys.flatMap(k=>{assert.ok(pins[k],k);return[[560,pins[k]],[560,[0,0]]];})
      .concat([[560*8,[0,0]]]))for(let j=0;j<count;j++){
      const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
      if(['indirect-p','write-v'].includes(stage)&&[0x9C,0xEE,0xE9,0xE7,0xA3,0xD4,0xD6].includes(ip)){
        const c=d.cells[core.tags.ik1302[[0xD4,0xD6].includes(ip)?21:22]];
        paths.push({stage,word:words,ip:ip.toString(16),owner:c.area+':'+c.word,
          a:p.r.filter((_,i)=>i<36&&i%3===0).reverse().map(n=>n.toString(16).toUpperCase()).join('')});
      }
      const outgoingBefore=m.names.slice(2).map(chip=>({chip,m:core.chips[chip].m,ids:core.tags[chip].slice()})),
        emitted=m.step(core,{...fixed,ik1302:key});
      for(const before of outgoingBefore)for(let n=0;n<42;n++){
        const c=d.cells[before.ids[n]],isProtected=c.area==='program'||String(c.field).startsWith('service'),
          isOtherBank=Number.isInteger(c.field)&&(c.area==='Ms'||c.area==='register'&&c.word!=='R0');
        if(isProtected||isOtherBank)protectedEmittedCells++;
        if(emitted[before.chip][n]!==before.m[n]){
          const change={stage,word:words,chip:before.chip,cell:c,before:before.m[n],after:emitted[before.chip][n]};
          if(isProtected&&!firstProtectedChange)firstProtectedChange=change;
          if(isOtherBank&&!firstOtherBankChange)firstOtherBankChange=change;
        }
      }
      const v=vector(core);
      for(let id=0;id<d.cells.length&&!firstProtectedChange;id++){
        const c=d.cells[id];if((c.area==='program'||String(c.field).startsWith('service'))&&v[id]!==initial[id])
          firstProtectedChange={stage,word:words,cell:c,before:initial[id],after:v[id]};
      }
      for(let id=0;id<d.cells.length&&!firstOtherBankChange;id++){
        const c=d.cells[id];if(Number.isInteger(c.field)&&(c.area==='Ms'||c.area==='register'&&c.word!=='R0')&&v[id]!==initial[id])
          firstOtherBankChange={stage,word:words,cell:c,before:initial[id],after:v[id]};
      }
      words++;
    }
    stages.push({stage,phaseBefore,phaseAfter:core.phase,start,end:describe()});
  }
  const marker=stages.find(s=>s.stage==='marker-exponent').end.visible.X,
    // Fractional-part shifts 8.F0000ab to F0000ab0; this prototype reserves
    // the two order digits only for a known 0xx positive-order input class.
    expected='0040F0000'+d.metadata.originalWords[15].slice(1,3)+'0',end=describe();
  const result={words,protectedEmittedCells,marker,expected,markerHasOriginalHeader:marker===expected,stages,paths,firstProtectedChange,firstOtherBankChange,
    finalBankChanges:end.banks.flatMap((w,i)=>w===d.metadata.originalWords[i]?[]:[{index:i,before:d.metadata.originalWords[i],after:w}]),
    boundary:'one automatic selected-order header-packing hypothesis, detached ALL5, no state repair; not native or universal writer success'};
  return options.includeCore?{...result,core,d}:result;
}
if(require.main===module){const out=run(process.argv[2]);console.log(JSON.stringify({...out,
  stages:out.stages.map(s=>({stage:s.stage,phaseBefore:s.phaseBefore,phaseAfter:s.phaseAfter,
    visible:s.end.visible,bankChanges:s.end.banks.flatMap((w,i)=>w===s.start.banks[i]?[]:[{index:i,before:s.start.banks[i],after:w}])}))}));}
module.exports={run,actions,pins};
