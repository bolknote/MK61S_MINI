#!/usr/bin/env node
'use strict';
// One continuous literal ALL5 execution with an explicit original-value
// ledger. The ordinary reserves are never counted as independent Ms.
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const {schedule}=require('./three-bank-escape-all5.cjs');
const {pagesAt}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const {FIRST,SECOND,THIRD,names,raw}=require('./cache-bc-head93-third-restore-plan.cjs');
const area=w=>['U','V','W','Q','P7','P8','P9','P10'].includes(w)?'Ms':['aux0','aux1'].includes(w)?'unclassified':'stack';
function verify(file,protocol,{includeCalculated=false}={}) {
  const d=JSON.parse(fs.readFileSync(file,'utf8')),entry=d.endpoints['packet-third-restore-FIRST'];
  assert.equal(d.schema,'mk61-third-restore-passive-v1');
  for(const [f,h] of Object.entries(d.metadata.frozenSha256))
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'),h);
  const core=m.make(entry),fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
  let primary={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
  const bankOf=()=>Object.fromEntries(['P7','P9','P10'].map(w=>[w,m.physical(core,d.cells,'Ms',w)]));
  let words=0,divergence=null;const stages=[];
  for(const action of protocol) {
    const changes=[],reads=[];let last=bankOf();
    for(const [count,key] of schedule(action))for(let j=0;j<count;j++) {
      const ip=core.chips.ik1302.r[36]+16*core.chips.ik1302.r[39];
      if(ip===0xD6) {
        const cell=d.cells[core.tags.ik1302[0]],source=Array.from({length:12},(_,k)=>core.chips.ik1302.m[3*k])
          .reverse().map(n=>n.toString(16).toUpperCase()).join('');
        reads.push({word:words,owner:cell.area+':'+cell.word,raw:source});
      }
      m.step(core,{...fixed,ik1302:key});
      for(const [reg,value] of [['R4',THIRD],['R6',SECOND],['R7',FIRST],['R8',THIRD]])
        assert.equal(m.physical(core,d.cells,'register',reg),value,'original full value in '+reg+' at '+words);
      const bank=bankOf();
      if(JSON.stringify(bank)!==JSON.stringify(last)){changes.push({word:words,ip,bank});last=bank;}
      words++;
    }
    primary=keyCall(primary,action.operand,action.lead,{kind:action.kind,preserved:p=>
      raw(p[7],0)===THIRD&&raw(p[9],0)===SECOND&&raw(p[10],0)===FIRST&&raw(p[11],0)===THIRD});
    assert.ok(primary.held,'PRIMARY original ordinary holders');
    if(!divergence)for(const field of ['r','m','st','s','s1','l','t','carry']) {
      if(JSON.stringify(core.chips.ik1302[field])!==JSON.stringify(primary.state[field])) {
        divergence={action,words,field,ALL5:core.chips.ik1302[field],PRIMARY:primary.state[field]};break;
      }
    }
    if(!divergence)for(const [j,w] of names.entries())assert.equal(m.physical(core,d.cells,area(w),w),raw(primary.pages[j]),'PRIMARY/ALL5 '+w);
    stages.push({action,words,changes,reads,bank:bankOf(),markers:names.filter(w=>m.physical(core,d.cells,area(w),w)[4]==='F')});
  }
  const bank=bankOf(),markers=stages.at(-1).markers;
  return{words,stages,bank,markers,numbers:Object.fromEntries(names.map(w=>[w,m.physical(core,d.cells,area(w),w)])),
    divergence,ledger:{FIRST:'R7',SECOND:'R6',THIRD:['R4','R8']},
    ...(includeCalculated?{calculatedEndpoint:{fullBefore:core.chips,tagsBefore:core.tags,
      numericOwner:[d.cells[core.tags.ik1302[22]].area+':'+d.cells[core.tags.ik1302[22]].word]}}:{}),
    goal:bank.P7===SECOND&&bank.P9===THIRD&&bank.P10===FIRST&&markers.join(',')==='aux0',
    boundary:'Literal ALL5 continuous fixed public-key schedule; every full original value retained through explicit ordinary reserves. Not native continuation or independent memory while reserves remain.'};
}
if(require.main===module) {
  const protocol=[{kind:'cx',operand:0,lead:0},{kind:'rcl',operand:9,lead:0},{kind:'swap',operand:0,lead:0},
    ...Array.from({length:5},()=>({kind:'rcl',operand:8,lead:0})),{kind:'cx',operand:0,lead:0}];
  console.log(JSON.stringify(verify(process.argv[2],protocol)));
}
module.exports={verify};
