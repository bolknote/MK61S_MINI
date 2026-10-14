#!/usr/bin/env node
'use strict';
// Literal detached ALL5 continuation, with no initial data edits or repairs.
// Optional fresh native capture supplies passive word/endpoint comparisons.
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const {FIRST,SECOND,THIRD}=require('./cache-bc-head93-third-restore-plan.cjs');
function run(file,nativeFile=null){
  const d=JSON.parse(fs.readFileSync(file,'utf8')),native=nativeFile?JSON.parse(fs.readFileSync(nativeFile,'utf8')):null;
  for(const [f,h] of Object.entries(d.metadata.frozenSha256))
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex'),h);
  const entry=d.endpoints['packet-third-write-P9'],core=m.make(entry);
  const observed=new Map(native?Object.entries(native.windows).filter(([n])=>n.startsWith('packet-third-restore-'))
    .flatMap(([,rows])=>rows.map(v=>[v.word,v])):[]);
  const fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
  let words=0,checked=0,bankStart=null;const stages=[];
  for(const [label,prefix,operand] of [['dropAux1',[11,9],[11,8]],['FIRST',[8,9],[9,8]]]){
    const events=[];
    for(const [count,key] of [[560,prefix],[7280,[0,0]],[560,operand],[8400,[0,0]]])for(let j=0;j<count;j++){
      const word=entry.word+words,v=observed.get(word),pins={...fixed,ik1302:key},p=core.chips.ik1302,ip=p.r[36]+16*p.r[39];
      if(v){m.compare(core,v.fullBefore,v.tagsBefore);assert.deepEqual(pins,m.pins(v));}
      if([0xD6,0xEE,0xE7,0xA8,0xA3].includes(ip))events.push({word,ip,
        owner:d.cells[core.tags.ik1302[22]],numeric:p.m.filter((_,k)=>k%3===1).slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('')});
      const emitted=m.step(core,pins);
      if(v){assert.deepEqual(emitted.ik1302,v.emitted);m.compare(core,v.fullAfter,v.tagsAfter);checked++;}
      for(const [reg,wanted] of [['R7',FIRST],['R6',SECOND],['R4',THIRD]])
        assert.equal(m.physical(core,d.cells,'register',reg),wanted,label+'/'+word+'/'+reg);
      const bank=Object.fromEntries(['P7','P9','P10'].map(w=>[w,m.physical(core,d.cells,'Ms',w)]));
      assert.equal(bank.P7,SECOND);
      const ready=bank.P9===FIRST&&bank.P10===THIRD;
      if(ready&&bankStart===null)bankStart=word;
      if(bankStart!==null)assert.ok(ready,label+'/'+word+'/three bank words');
      words++;
    }
    stages.push({label,events,bank:Object.fromEntries(['P7','P9','P10'].map(w=>[w,m.physical(core,d.cells,'Ms',w)]))});
    if(native){const end=native.endpoints['packet-third-restore-'+label];
      assert.equal(entry.word+words,end.word);m.compare(core,end.fullBefore,end.tagsBefore);}
  }
  assert.equal(words,33600);assert.ok(bankStart!==null);
  // A separately calculated ordinary CX is a negative boundary, not part
  // of the positive native tail. Its A3 corrupts SECOND's order in P7.
  let cxWords=0,loss=null;
  for(const [count,key] of [[560,[10,8]],[7840,[0,0]]])for(let j=0;j<count;j++){
    const p=core.chips.ik1302,ip=p.r[36]+16*p.r[39],owner=d.cells[core.tags.ik1302[22]];
    const v=observed.get(entry.word+words+cxWords),pins={...fixed,ik1302:key};
    if(v){m.compare(core,v.fullBefore,v.tagsBefore);assert.deepEqual(pins,m.pins(v));}
    const output=m.step(core,pins);
    if(v){assert.deepEqual(output.ik1302,v.emitted);m.compare(core,v.fullAfter,v.tagsAfter);checked++;}
    const bank=Object.fromEntries(['P7','P9','P10'].map(w=>[w,m.physical(core,d.cells,'Ms',w)]));
    if(!loss&&(bank.P7!==SECOND||bank.P9!==FIRST||bank.P10!==THIRD))loss={offset:cxWords,ip,owner,bank};
    cxWords++;
  }
  assert.equal(cxWords,8400);assert.equal(loss.offset,2227);assert.equal(loss.ip,0xA3);
  assert.equal(loss.owner.area,'Ms');assert.equal(loss.owner.word,'P7');
  assert.deepEqual(loss.bank,{P7:'FFF024681357',P9:FIRST,P10:THIRD});
  const cxNativeEnd=native?.endpoints['packet-third-restore-CX'];
  if(cxNativeEnd){assert.equal(entry.word+words+cxWords,cxNativeEnd.word);m.compare(core,cxNativeEnd.fullBefore,cxNativeEnd.tagsBefore);}
  if(native)assert.equal(checked,observed.size);
  return{directALL5Words:words,nativeMatches:checked,bankStart,stages,
    negativeCX:{directALL5Words:cxWords,nativeEndpointChecked:!!cxNativeEnd,loss,
      boundary:cxNativeEnd?'fresh native CX/all5 endpoint and passive words matched; not global impossibility':
        'literal ALL5 continuation only; not an extra native command/global impossibility'},
    boundary:'three full Ms words reached; reserves remain and P9 header is not canonical, not a third read/work cycle or full K1/K2'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],process.argv[3]||null)));
module.exports={run};
