#!/usr/bin/env node
'use strict';
// Whole closed cycle literal ALL5; P9 is INITIAL DATA only, never written
// into a real emulator. Baseline returns to the real exact starting state.
const fs=require('node:fs'),assert=require('node:assert/strict');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const masks=require('./cache-bc-head93-rom-memory-masks.cjs').masks;
const d=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
assert.equal(d.metadata.profile,'p7-normal-retain-both');
const FIRST='007012345678',SECOND='007024681357';
const THIRD=process.argv.find(v=>v.startsWith('--third='))?.slice(8)||'950013579246';
assert.match(THIRD,/^[0-9A-F]{12}$/);
const rows=[['normal-clear','cx'],['normal-erase6','store',9],['normal-erase7','store',10],
  ['normal-aux0','rcl',6],['normal-port5','store',8],['normal-Y','rcl',8],['normal-X1','rcl',11],
  ...Array.from({length:3},(_,i)=>['normal-shift'+(i+1),'rcl',10]),
  ['normal-clearP8','cx',0,12],['normal-header','rcl',8,6],['normal-clearW','rcl',5],
  ...Array.from({length:4},(_,i)=>['normal-flush'+(i+1),'rcl',4]),['normal-port5zero','store',5],
  ['math-clear','cx'],['math-two','digit',2],['math-enter','enter'],['math-three','digit',3],
  ['math-plus','plus'],['math-lastx','lastx'],['math-clear2','cx'],
  ...Array.from({length:4},(_,i)=>['math-flush'+(i+1),'rcl',0]),
  ...Array.from({length:4},(_,i)=>['second-F'+(i+1),'rcl',3]),['second-U','rcl',7],['second-V','rcl',7],
  ['second-clearY','cx'],...Array.from({length:3},(_,i)=>['second-front'+(i+1),'rcl',4]),['second-output','store',6],
  ...Array.from({length:3},(_,i)=>['first-Y'+(i+1),'rcl',3]),['first-P8','rcl',10],
  ['first-Wzero1','rcl',10],['first-Wzero2','rcl',10],['first-aux0','rcl',6],
  ['first-T','rcl',7],['first-X1','rcl',7],['first-Wzero','cx'],['first-X1zero','rcl',4],
  ...Array.from({length:4},(_,i)=>['first-flush'+(i+1),'rcl',5]),['first-read','lastx'],['first-output','store',10],
  ['end-idle','idle']];
const operand=n=>n<10?[n+2,1]:[n-3,8];
function parts(kind,n=0,lead=0) {
  if(kind==='idle')return[[6720,[0,0]]];
  const single={cx:[10,8],enter:[11,8],plus:[2,8],digit:operand(n)};
  const body=single[kind]?[[560,single[kind]],[7840,[0,0]]]:[
    [560,kind==='lastx'?[11,9]:kind==='store'?[6,9]:[8,9]],[7280,[0,0]],
    [560,kind==='lastx'?[11,8]:operand(n)],[8400,[0,0]]];
  return lead?[[lead,[0,0]],...body,[30-lead,[0,0]]]:body;
}
function run(third,incoming=null,pass=1) {
  const entry=d.endpoints['packet-p7-first-output'],core=incoming?structuredClone(incoming):m.make(entry);
  if(third&&!incoming)for(const chip of m.names)core.tags[chip].forEach((id,j)=>{
    const c=d.cells[id];if(c.area==='Ms'&&c.word==='P9'&&Number.isInteger(c.field))core.chips[chip].m[j]=parseInt(THIRD[11-c.field],16);
  });
  const original=structuredClone(core),fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[core.chips[n].keyX,core.chips[n].keyY]]));
  let words=0,firstDiff=null;
  for(const [stage,kind,n,lead] of rows) {
    for(const [count,key] of parts(kind,n,lead))for(let j=0;j<count;j++) {
      const possible=third?m.names.slice(2).filter(chip=>d.cells[core.tags[chip][22]].area==='Ms'&&
        d.cells[core.tags[chip][22]].word==='P9').map(chip=>({chip,
          ip:core.chips[chip].r[36]+16*core.chips[chip].r[39],old:core.chips[chip].m.slice()}))
        .filter(v=>masks(v.chip,v.ip).write.some(k=>k<=34&&k%3===1)):[];
      const outputs=m.step(core,{...fixed,ik1302:key});
      if(third&&m.physical(core,d.cells,'Ms','P9')!==THIRD){
        firstDiff={stage,offset:words,actual:m.physical(core,d.cells,'Ms','P9'),
          writers:possible.map(v=>({chip:v.chip,ip:v.ip.toString(16).toUpperCase(),
            changed:v.old.flatMap((n,k)=>outputs[v.chip][k]!==n?[k]:[])}))};break;
      }
      words++;
    }
    if(firstDiff)break;
    if(stage==='normal-port5zero') {
      for(const key of '0123456789ABCDE')assert.ok(![FIRST,SECOND,THIRD].includes(m.physical(core,d.cells,'register','R'+key)),
        'no ordinary numerical reserve at the work point');
    }
    if(stage==='math-plus') {
      assert.equal(m.physical(core,d.cells,'stack','Y'),'000050000000');
      assert.equal(m.physical(core,d.cells,'stack','X'),'000030000000');
    }
    if(['normal-port5zero','second-output','first-output'].includes(stage))
      console.log('CALCULATED',third?'INITIAL-P9-HYPOTHESIS':'baseline',stage,words,
        JSON.stringify(Object.fromEntries(['P7','P9','P10'].map(w=>[w,m.physical(core,d.cells,'Ms',w)]))));
  }
  let equal=false;
  if(!firstDiff) {
    assert.equal(words,880380);
    try{m.compare(core,original.chips,original.tags);equal=true;}catch(error){if(!third)throw error;}
    assert.equal(m.physical(core,d.cells,'Ms','P7'),SECOND);
    assert.equal(m.physical(core,d.cells,'Ms','P10'),FIRST);
    assert.equal(m.physical(core,d.cells,'register','R6'),SECOND);
    assert.equal(m.physical(core,d.cells,'register','R7'),FIRST);
  }
  console.log(JSON.stringify({conditional:third,pass,directALL5Words:words,firstDifference:firstDiff,
    wholeCoreClosed:equal,P9:m.physical(core,d.cells,'Ms','P9'),
    boundary:third?'ONLY INITIAL-DATA P9 full-cycle hypothesis; native third writer/reader/arbitrary bank/full K1/K2 missing':'full closed cycle literal ALL5 returned exactly to genuine captured state; no skips/repairs'}));
  if(third&&!firstDiff&&pass===1)run(true,core,2);
  if(third&&pass===2)assert.ok(equal,'do not relabel payload retention as whole-core closure');
}
if(!process.argv.includes('--only-hypothesis'))run(false);
run(true);
