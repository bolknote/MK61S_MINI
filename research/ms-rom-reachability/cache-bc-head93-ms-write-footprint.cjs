#!/usr/bin/env node
'use strict';
// ROM-conservative memory-write mask: BOTH possible L branches are included.
// Native windows provide visited chip/IP/carrier contexts, not hypothetical
// marker states. This is a structural candidate audit, not a second stored
// number or a universal all-prefix/no-write theorem.
const assert=require('node:assert/strict');
const rom=require('/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs');
const {run}=require('./cache-bc-head93-canonical-steady-native.cjs');
const specs={ik1302:rom.ИК1302,ik1303:rom.ИК1303,ik1306:rom.ИК1306};
function possibleWrites(spec,ip) {
  const word=spec.команды[ip],result=[];assert.notEqual(word,undefined);
  for(let j=0;j<42;j++) {
    const nine=Math.floor(j/9);
    let sync=nine<3?word&127:nine===3?(word>>>7)&127:(word>>>14)&255;
    if(nine===4&&sync>31)sync=95;
    const sub=j<6?j:j<21?j%3+3:j%9;
    const n=spec.синхропрограммы[sync*9+sub]&63;
    const variants=n<=59?[n]:[(n-60)*2+60,(n-60)*2+61];
    if(variants.some(v=>((spec.микрокоманды[v]>>>20)&1)!==0))result.push(j);
  }
  return result;
}
function audit(data,labels) {
  const union=Object.fromEntries(['U','V','W','Q','P7','P8','P9','P10'].map(n=>[n,new Set()]));
  const contexts=new Map(),cache=new Map();let words=0;
  for(const label of labels)for(const v of data.windows[label]) {
    words++;
    for(const [chip,spec] of Object.entries(specs)) {
      const before=v.fullBefore[chip],ip=before.r[36]+16*before.r[39],key=chip+'/'+ip;
      if(!cache.has(key))cache.set(key,possibleWrites(spec,ip));
      const mask=cache.get(key),owned=new Map();
      for(let j=0;j<42;j++) {
        const cell=data.cells[v.tagsBefore[chip][j]];
        if(cell.area!=='Ms'||!Number.isInteger(cell.field))continue;
        const name=cell.word;
        if(!owned.has(name))owned.set(name,[]);
        if(mask.includes(j)) {owned.get(name).push(cell.field);union[name].add(cell.field);}
      }
      for(const [name,fields] of owned) {
        const id=name+'/'+key;if(!contexts.has(id))contexts.set(id,{name,chip,ip,fields:new Set(),visits:0});
        const item=contexts.get(id);item.visits++;for(const f of fields)item.fields.add(f);
      }
    }
  }
  const result={coveredNativeWords:words,windows:labels.length,
    possibleNumericWriteFields:Object.fromEntries(Object.entries(union).map(([n,s])=>[n,[...s].sort((a,b)=>a-b)])),
    P9Contexts:[...contexts.values()].filter(c=>c.name==='P9').map(c=>({...c,
      ipHex:c.ip.toString(16).toUpperCase().padStart(2,'0'),fields:[...c.fields].sort((a,b)=>a-b)})),
    boundary:'visited native windows and ROM-union L branches only; mask may overapproximate real writes, not all native waits or a stored second number'};
  return result;
}
if(require.main===module) {
  const data=run({proof:true});
  const labels=Object.keys(data.windows).filter(n=>n.startsWith('packet-repeat2-')||n==='packet-idle');
  console.log(JSON.stringify(audit(data,labels)));
}
module.exports={possibleWrites,audit};
