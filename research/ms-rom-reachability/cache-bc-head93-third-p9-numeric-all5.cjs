#!/usr/bin/env node
'use strict';
// Literal ALL5, independently checked on native words. Never an MK61
// instance/state import. Recalculate every one of 277200 key-schedule words.
const fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const FIRST='007012345678',SECOND='007024681357',THIRD='950013579246';
const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
assert.equal(d.metadata.profile,'p7-normal-retain-both');
for(const [file,hash] of Object.entries(d.metadata.frozenSha256))
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex'),hash);
const sequence=[...Array.from({length:3},(_,i)=>['Y'+(i+1),3,'rcl']),['P8',10,'rcl'],
  ['Wzero1',10,'rcl'],['Wzero2',10,'rcl'],['aux0',6,'rcl'],['T',7,'rcl'],['X1',7,'rcl'],
  ['Wzero',0,'cx'],['X1zero',4,'rcl'],...Array.from({length:4},(_,i)=>['flush'+(i+1),5,'rcl']),
  ['read',0,'lastx'],['output',10,'store']];
const raw=a=>a.slice(0,12).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const operand=n=>n<10?[n+2,1]:[n-3,8];
function run(third) {
  const entry=d.endpoints['packet-p7-read-output'],end=d.endpoints['packet-p7-first-output'];
  const core=m.make(entry);
  if(third)for(const chip of m.names)core.tags[chip].forEach((id,j)=>{
    const c=d.cells[id];if(c.area==='Ms'&&c.word==='P9'&&Number.isInteger(c.field))
      core.chips[chip].m[j]=parseInt(THIRD[11-c.field],16);
  });
  const observed=new Map(Object.entries(d.windows).filter(([n])=>n.startsWith('packet-p7-first-'))
    .flatMap(([,rows])=>rows.map(v=>[v.word,v])));
  const fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
  let words=0,checked=0;
  for(const [suffix,n,kind] of sequence) {
    const parts=kind==='cx'?[[560,[10,8]],[7840,[0,0]]]:[
      [560,kind==='lastx'?[11,9]:kind==='store'?[6,9]:[8,9]],[7280,[0,0]],
      [560,kind==='lastx'?[11,8]:operand(n)],[8400,[0,0]]];
    for(const [count,key] of parts)for(let j=0;j<count;j++) {
      const v=third?null:observed.get(entry.word+words),pins={...fixed,ik1302:key};
      if(v){m.compare(core,v.fullBefore,v.tagsBefore);assert.deepEqual(pins,m.pins(v));}
      const before=third?m.names.slice(2).map(chip=>({chip,ip:core.chips[chip].r[36]+16*core.chips[chip].r[39],
        owner:d.cells[core.tags[chip][22]],old:raw(core.chips[chip].m.filter((_,k)=>k%3===1))})):null;
      const output=m.step(core,pins);
      if(v){assert.deepEqual(output.ik1302,v.emitted);m.compare(core,v.fullAfter,v.tagsAfter);checked++;}
      if(third&&m.physical(core,d.cells,'Ms','P9')!==THIRD) {
        const writers=before.map(b=>({...b,new:raw(output[b.chip].filter((_,k)=>k%3===1))})).filter(b=>b.old!==b.new);
        console.log(JSON.stringify({conditional:true,failedAt:{word:entry.word+words,stage:suffix,
          actual:m.physical(core,d.cells,'Ms','P9'),writers},boundary:'failed INITIAL P9 DATA hypothesis, not native third storage/global no-go'}));
        return;
      }
      words++;
    }
  }
  assert.equal(words,277200);
  if(!third){assert.equal(checked,observed.size);m.compare(core,end.fullBefore,end.tagsBefore);}
  const final=Object.fromEntries(['P7','P9','P10'].map(w=>[w,m.physical(core,d.cells,'Ms',w)]));
  assert.equal(final.P7,SECOND);assert.equal(final.P10,FIRST);
  assert.equal(m.physical(core,d.cells,'register','R6'),SECOND);assert.equal(m.physical(core,d.cells,'register','R7'),FIRST);
  console.log(JSON.stringify({conditional:third,directALL5Words:words,nativeMatches:checked,final,
    boundary:third?'P9 data-only hypothesis survives FIRST reader; missing native write/read/fullcycle/K1/K2':'ENTIRE native FIRST reader/all5 endpoint verified without skips/repairs'}));
}
run(false);run(true);
