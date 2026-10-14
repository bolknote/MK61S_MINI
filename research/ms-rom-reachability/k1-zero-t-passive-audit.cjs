#!/usr/bin/env node
'use strict';
// Passive numeric arrays into the literal ALL5 interpreter. No MK61 object,
// no imported calculator state, no repair at any native comparison point.
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
const MS=['U','V','W','Q','P7','P8','P9','P10'];
function load(file) {
  const d=JSON.parse(fs.readFileSync(file,'utf8'));assert.equal(d.schema,'k1-zero-capture-passive-v1');
  for(const [p,h] of Object.entries(d.metadata.frozenSha256))
    assert.equal(crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex'),h);
  return d;
}
function vector(core) {
  const out=Array(630);
  for(const chip of model.names)for(let i=0;i<core.tags[chip].length;i++)out[core.tags[chip][i]]=core.chips[chip].m[i];
  assert.ok(Array.from(out).every(Number.isInteger));return out;
}
function reader(d) {
  const groups=new Map();
  for(let tag=0;tag<d.cells.length;tag++) {
    const c=d.cells[tag];if(Number.isInteger(c.field)) {
      const key=c.area+':'+c.word;if(!groups.has(key))groups.set(key,Array(12));groups.get(key)[c.field]=tag;
    }
  }
  for(const ids of groups.values())assert.ok(Array.from(ids).every(Number.isInteger));
  return{groups,word:(v,area,name)=>{const ids=groups.get(area+':'+name);assert.ok(ids,area+':'+name);
    return ids.slice().reverse().map(tag=>v[tag].toString(16).toUpperCase()).join('');}};
}
function oldWord(r,v,d,name) {
  if(MS.includes(name))return r.word(v,'Ms',name);
  if(name==='marker'||name==='control')return r.word(v,'unclassified',name==='marker'?'aux0':'aux1');
  return r.word(v,'stack',d.metadata.logicalMap[name]);
}
function run(file) {
  const d=load(file),start=d.endpoints['capture-start'],end=d.endpoints['capture-end'],core=model.make(start),r=reader(d);
  const initial=vector(core),protectedIds=d.cells.flatMap((c,i)=>c.area==='program'||String(c.field).startsWith('service')?[i]:[]);
  const unchangedIds=d.cells.flatMap((c,i)=>Number.isInteger(c.field)&&(c.area==='Ms'||(c.area==='register'&&c.word!=='R0'))?[i]:[]);
  const storedKeys=[...r.groups.keys()].filter(k=>k.startsWith('register:')||k.startsWith('Ms:')||k.startsWith('stack:'));
  const records=new Map(Object.values(d.windows).flat().map(v=>[v.word,v]));
  const fixed=Object.fromEntries(model.names.slice(2).map(n=>[n,[start.fullBefore[n].keyX,start.fullBefore[n].keyY]]));
  let words=0,matched=0;
  for(const segment of d.schedule)for(let j=0;j<segment.count;j++) {
    const actual=records.get(words),pins={...fixed,ik1302:segment.key};
    if(actual){model.compare(core,actual.fullBefore,actual.tagsBefore);assert.deepEqual(pins,model.pins(actual));}
    const out=model.step(core,pins);
    if(actual){assert.deepEqual(out.ik1302,actual.emitted);model.compare(core,actual.fullAfter,actual.tagsAfter);matched++;}
    const values=vector(core);
    for(const id of protectedIds)assert.equal(values[id],initial[id],'program/service '+words+'/'+id);
    for(const id of unchangedIds)assert.equal(values[id],initial[id],'original Ms/other14 '+words+'/'+id);
    const live=new Set(storedKeys.map(k=>{const at=k.indexOf(':');return r.word(values,k.slice(0,at),k.slice(at+1));}));
    for(const original of d.metadata.originalWords)assert.ok(live.has(original),'lost original full word '+original+' at '+words);
    words++;
  }
  assert.equal(words,d.metadata.protocolWords);assert.equal(matched,records.size);
  model.compare(core,end.fullBefore,end.tagsBefore);
  const values=vector(core),p=core.chips.ik1302;
  return{words,nativeWordsMatched:matched,ALL5EndpointMatched:true,phase:core.phase,
    oldVisible:Object.fromEntries(['X1','X','Y','Z','T'].map(n=>[n,oldWord(r,values,d,n)])),
    P0:r.word(values,'register','R0'),Ms:Object.fromEntries(MS.map(n=>[n,r.word(values,'Ms',n)])),
    C8Packet:{IP:p.r[36]+16*p.r[39],R25:p.r[25],R31:p.r[31],R38:p.r[38],R26:p.r[26],
      R29:p.r[29],R32:p.r[32],R35:p.r[35],R41:p.r[41],R2:p.r[2]},
    everyWord:{all23OriginalsLive:true,MsAndOther14Held:true,programAndAllServicesHeld:true},
    boundary:'Literal complete recorded native half-pair cadence; no continuation, reverse V write, working exit, or full K1.'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={load,vector,reader,oldWord,run,MS};
