#!/usr/bin/env node
'use strict';
// Literal ALL5 selected structural controls. Snapshot arrays are passive
// inputs to the detached model, never imported into an MK61 instance.
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const {pagesAt}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const {keyCall}=require('./cache-bc-head93-second-key-prefix-plan.cjs');
const {FIRST,SECOND,THIRD,names}=require('./cache-bc-head93-third-restore-plan.cjs');
const pins=n=>n<10?[n+2,1]:[n-3,8];
function schedule({kind,operand,lead}) {
  const simple=['cx','enter','swap'].includes(kind);
  return simple?[[lead,[0,0]],[560,kind==='cx'?[10,8]:kind==='swap'?[6,8]:[11,8]],[7840,[0,0]],
    [lead?30-lead:0,[0,0]]]:[[lead,[0,0]],[560,kind==='lastx'?[11,9]:kind==='nop'?[10,9]:[8,9]],
    [7280,[0,0]],[560,kind==='lastx'?[11,8]:pins(operand)],[8400,[0,0]],[lead?30-lead:0,[0,0]]];
}
function run(file) {
  const d=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(d.schema,'mk61-third-restore-passive-v1');
  for(const [f,h] of Object.entries(d.metadata.frozenSha256))
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'),h);
  const cases=[
    ['post-lastx','packet-third-restore-FIRST',{kind:'lastx',operand:0,lead:0}],
    ['post-phase-cx','packet-third-restore-FIRST',{kind:'cx',operand:0,lead:12}],
    ['post-third-recall','packet-third-restore-FIRST',{kind:'rcl',operand:9,lead:18}],
    ['pre-F-transfer','packet-third-restore-dropAux1',{kind:'rcl',operand:8,lead:18}],
    ['pre-LastX-marker','packet-third-restore-dropAux1',{kind:'lastx',operand:0,lead:0}],
    ['pre-NOP-format','packet-third-restore-dropAux1',{kind:'nop',operand:0,lead:0}],
    ['pre-FIRST-control','packet-third-restore-dropAux1',{kind:'rcl',operand:12,lead:0}],
  ],results=[];
  for(const [name,at,action] of cases) {
    const entry=d.endpoints[at],core=m.make(entry),fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
    const inlet={state:entry.fullBefore.ik1302,pages:pagesAt(d,entry),here:names.indexOf(entry.numericOwner[0].split(':')[1])};
    const bankOf=()=>Object.fromEntries(['P7','P9','P10'].map(w=>[w,m.physical(core,d.cells,'Ms',w)]));
    const holdersOf=()=>Object.fromEntries([['R4',THIRD],['R6',SECOND],['R7',FIRST],['R8',THIRD]]
      .map(([reg])=>[reg,m.physical(core,d.cells,'register',reg)]));
    const expected=bankOf(),holderExpected=holdersOf();
    let words=0,loss=null;const route=[];
    for(const [count,key] of schedule(action))for(let j=0;j<count;j++) {
      const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39],owner=d.cells[core.tags.ik1302[22]];
      if([0x9C,0x9D,0x9E,0xA3,0xEE,0xD6,0xE7,0xA8].includes(ip))
        route.push({word:words,ip,owner:owner.area+':'+owner.word,header:[p.m[31],p.m[34]]});
      m.step(core,{...fixed,ik1302:key});
      const bank=bankOf();
      assert.deepEqual(holdersOf(),holderExpected,name+'/ordinary holders/'+words);
      if(!loss&&Object.entries(expected).some(([w,v])=>bank[w]!==v))loss={word:words,ip,owner:owner.area+':'+owner.word,bank};
      words++;
    }
    const primary=keyCall(inlet,action.operand,action.lead,{kind:action.kind,preserved:()=>true});
    assert.equal(words,primary.words,name+'/whole schedule');
    for(const field of ['r','m','st','s','s1','l','t','carry'])
      assert.deepEqual(core.chips.ik1302[field],primary.state[field],name+'/ALL5 versus PRIMARY/'+field);
    for(const [j,w] of names.entries()) {
      const area=['U','V','W','Q','P7','P8','P9','P10'].includes(w)?'Ms':['aux0','aux1'].includes(w)?'unclassified':'stack';
      const raw=Array.from({length:12},(_,k)=>primary.pages[j][1+3*k]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
      assert.equal(m.physical(core,d.cells,area,w),raw,name+'/ALL5 versus PRIMARY/'+w);
    }
    const gates=route.filter(p=>p.ip===0x9C);
    results.push({name,action,words,firstBankChange:loss,bank:bankOf(),holders:holdersOf(),
      markers:names.filter(w=>m.physical(core,d.cells,['U','V','W','Q','P7','P8','P9','P10'].includes(w)?'Ms':['aux0','aux1'].includes(w)?'unclassified':'stack',w)[4]==='F'),
      gates:{count:gates.length,first:gates.slice(0,2),last:gates.slice(-2)},
      events:route.filter(p=>![0x9C,0x9D,0x9E].includes(p.ip))});
  }
  return{results,boundary:'Literal full ALL5 schedules from passive native endpoints with every-word holders, PRIMARY endpoints/all 15 numeric pages matched. No new native keys or usable three-word cycle.'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run,schedule};
