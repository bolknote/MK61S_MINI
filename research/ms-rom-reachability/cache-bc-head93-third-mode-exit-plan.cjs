#!/usr/bin/env node
'use strict';
// Two purpose-selected mode escapes from the actual three-bank endpoint.
// Literal ALL5 only, no calculator import, control edit or key sweep.
const fs=require('node:fs'),assert=require('node:assert/strict');
const m=require('./cache-bc-head93-numeric-all5-model.cjs');
const {FIRST,SECOND,THIRD}=require('./cache-bc-head93-third-restore-plan.cjs');
function run(file){
  const d=JSON.parse(fs.readFileSync(file,'utf8'));
  assert.equal(d.schema,'mk61-third-restore-passive-v1');
  const entry=d.endpoints['packet-third-restore-FIRST'];
  const bankOf=core=>Object.fromEntries(['P7','P9','P10'].map(w=>[w,m.physical(core,d.cells,'Ms',w)]));
  const wanted={P7:SECOND,P9:FIRST,P10:THIRD};
  const results=[];
  for(const [name,commands] of [['auto-only',[['AUTO',[11,9],[8,8]],['CX',[10,8]]]],
    ['program-auto',[['PROGRAM',[11,9],[9,8]],['AUTO',[11,9],[8,8]],['CX',[10,8]]]]]){
    const core=m.make(entry),fixed=Object.fromEntries(m.names.slice(2).map(n=>[n,[entry.fullBefore[n].keyX,entry.fullBefore[n].keyY]]));
    let words=0,loss=null;const stages=[];
    outer:for(const [label,prefix,operand] of commands){
      const parts=operand?[[560,prefix],[7280,[0,0]],[560,operand],[8400,[0,0]]]:[[560,prefix],[7840,[0,0]]];
      for(const [count,key] of parts)for(let j=0;j<count;j++){
        const before=m.names.slice(2).map(chip=>({chip,ip:core.chips[chip].r[36]+16*core.chips[chip].r[39],
          owner:d.cells[core.tags[chip][22]]}));
        m.step(core,{...fixed,ik1302:key});words++;
        const bank=bankOf(core);
        if(Object.entries(wanted).some(([w,n])=>bank[w]!==n)){
          loss={stage:label,offset:words-1,bank,controllers:before};break outer;
        }
      }
      stages.push({label,modeR2:core.chips.ik1302.r[2],bank:bankOf(core),
        markers:['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y']
          .filter(w=>m.physical(core,d.cells,['U','V','W','Q','P7','P8','P9','P10'].includes(w)?'Ms':
            ['aux0','aux1'].includes(w)?'unclassified':'stack',w)[4]==='F')});
    }
    assert.ok(loss,'known mode escape must not be counted as a successful third work cycle');
    assert.equal(loss.stage,'CX');assert.deepEqual(loss.bank,{P7:'FFF024681357',P9:FIRST,P10:THIRD});
    assert.ok(loss.controllers.some(v=>v.chip==='ik1302'&&v.ip===0xA3&&v.owner.area==='Ms'&&v.owner.word==='P7'));
    results.push({name,directALL5Words:words,held:loss===null,loss,stages});
  }
  return{results,boundary:'two fixed mode-escape hypotheses in detached ALL5, not native mode exit/third read/full K1/K2'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2])));
module.exports={run};
