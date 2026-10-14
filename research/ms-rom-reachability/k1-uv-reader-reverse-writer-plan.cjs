#!/usr/bin/env node
'use strict';
// One ROM-directed reverse-writer construction, not an unconstrained key search.
// Baseline is a complete independently recalculated native U/V reader. This
// detached continuation is a hypothesis until a fresh key-only native mirror.
const assert=require('node:assert/strict');
const {run:prefix}=require('./k1-zero-uv-reader-all5-check.cjs');
const {vector,reader,oldWord}=require('./k1-zero-t-passive-audit.cjs');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const writerTail=[...['Сx','K','-','ВП','K','0'].map((k,i)=>['marker-'+i,[k],12]),
  ['carrier-exponent',['ВП']],['carrier-four',['4']],['save-carrier',['X→П','0']],
  ['push-carrier',['П→X','0']],['lastx-first-f',['F']],['lastx-first',['В↑']],
  ['lastx-second-f',['F']],['lastx-second',['В↑']],['indirect-p',['K','X→П',',']],
  ['p-to-t-marker',['П→X','0']],['write-v',['↔']],['drop-marker',['П→X','0']],
  ['rotate-0',['F',',']],['rotate-1',['F',',']],['rotate-2',['F',',']],['restore-v',['X→П','0']]];
const recipes={
  'naive-first-roll':[['copy-u-top',['F',',']],['old-p0-a',['П→X','0']],['old-p0-b',['П→X','0']]],
  // Canonical ROLL is (X,Y,Z,T)->(Y,Z,T,X). Two ROLLs discard only
  // the disposable request header on RCL; ENTER makes p/p/v/u for the maker.
  'payload-tail':[['tail-roll-0',['F',',']],['tail-roll-1',['F',',']],['old-p0',['П→X','0']],['duplicate-p',['В↑']]]
};
const suffix=[...recipes['payload-tail'],...writerTail];
const pins={'F':[11,9],',':[7,8],'П→X':[8,9],'X→П':[6,9],'0':[2,1],'4':[6,1],'+':[2,8],
  'Сx':[10,8],'K':[10,9],'-':[3,8],'ВП':[9,8],'В↑':[11,8],'↔':[6,8]};
function run(file,recipe='payload-tail'){
  assert.ok(Object.hasOwn(recipes,recipe));
  const baseline=prefix(file,true),{core,d}=baseline,r=reader(d),initial=vector(core),
    fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[core.chips[n].keyX,core.chips[n].keyY]])),
    bankNames=[...r.groups.keys()].filter(k=>/^(register|Ms|stack):/.test(k));
  assert.equal(d.schema,'k1-zero-uv-reader-passive-v1','this construction requires the native U/V reader boundary');
  let words=0,firstBankWordAbsence=null,firstProtectedChange=null;
  const stages=[],paths=[];
  const state=()=>{const v=vector(core);return{visible:Object.fromEntries(['X','Y','Z','T','X1'].map(w=>[w,oldWord(r,v,d,w)])),
    P0:r.word(v,'register','R0'),U:r.word(v,'Ms','U'),V:r.word(v,'Ms','V')};};
  for(const [stage,keys,frames=8] of [...recipes[recipe],...writerTail]){
    const start=state();
    for(const [count,key] of keys.flatMap(k=>{assert.ok(pins[k],k);return[[560,pins[k]],[560,[0,0]]];})
      .concat([[frames*560,[0,0]]]))for(let j=0;j<count;j++){
      const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
      if([0xD6,0xD4,0xEE,0xE9,0xA3,0xE7].includes(ip)){
        const c=d.cells[core.tags.ik1302[ip===0xD6||ip===0xD4?21:22]];
        paths.push({word:words,stage,ip:ip.toString(16),owner:c.area+':'+c.word,
          value:m.physical(core,d.cells,c.area,c.word),a:p.r.filter((_,i)=>i<36&&i%3===0).reverse().map(n=>n.toString(16).toUpperCase()).join('')});
      }
      m.step(core,{...fixed,ik1302:key});const values=vector(core),live=new Set(bankNames.map(k=>{
        const at=k.indexOf(':');return r.word(values,k.slice(0,at),k.slice(at+1));}));
      // A whole word can be temporarily in processor R/ST rather than a bank.
      // Absence from these stored-word groups is NOT irreversible state loss.
      const absent=d.metadata.originalWords.filter(w=>!live.has(w));
      if(absent.length&&!firstBankWordAbsence)firstBankWordAbsence={word:words,stage,absent};
      for(let id=0;id<d.cells.length&&!firstProtectedChange;id++){
        const c=d.cells[id];if((c.area==='program'||String(c.field).startsWith('service'))&&values[id]!==initial[id])
          firstProtectedChange={word:words,stage,cell:c,before:initial[id],after:values[id]};
      }
      words++;
    }
    stages.push({stage,start,end:state()});
  }
  const values=vector(core),banks=Array.from({length:15},(_,i)=>r.word(values,'register','R'+i.toString(16).toUpperCase()))
    .concat(['U','V','W','Q','P7','P8','P9','P10'].map(w=>r.word(values,'Ms',w))),expected=d.metadata.originalWords.slice();
  [expected[0],expected[16]]=[expected[16],expected[0]];
  return{recipe,prefixWords:baseline.directALL5Words,suffixWords:words,stages,paths,firstBankWordAbsence,firstProtectedChange,
    finalBankChanges:banks.flatMap((w,i)=>w!==d.metadata.originalWords[i]?[{index:i,before:d.metadata.originalWords[i],after:w}]:[]),
    exactPair:banks.every((w,i)=>w===expected[i]),
    boundary:'one derived detached ALL5 writer hypothesis; not a native new pair, universal proof or full K1'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],process.argv[3])));
module.exports={suffix,pins,run,writerTail,recipes};
