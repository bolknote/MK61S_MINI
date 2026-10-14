#!/usr/bin/env node
'use strict';
// Conditional closing tail for the guarded upper rotation. The accompanying
// tests audit its exact write set; this is not K1 or a universal input claim.
const rotate=require('./k1-u-reserve-zero-rotate.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...rotate.defaults};
const stages=['close/lift-u','close/save-u','close/swap-q','close/save-q','close/drop-z','close/drop-t'];
function finish(c,o={},record=()=>{}) {
  rotate.finish(c,{...o,clearMarker:false},record);
  const actions=[['+'],['K','0'],['↔'],['K','0'],['П→X','1'],['П→X','1']];
  for(const [i,keys] of actions.entries()) {
    if(i>=(o.closeSteps??actions.length))break;
    const phase=o.closePhases?.[i]??[2,0,2,0,0,0][i];
    if(phase){record(stages[i]+'/phase');c.runFrames(phase);}
    stack.act(c,record,stages[i],keys,o.closeWaits?.[i]??8);
  }
  if(o.verifyExit) {
    stack.act(c,record,'post/manual',['Сx','2','В↑','3','+']);
    stack.act(c,record,'post/zero',['Сx']);
    stack.act(c,record,'post/program',['В/О','С/П'],12);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0',...[0,1,2,3].map(i=>'u-reserve/tail-'+i),...stages]);
module.exports={defaults,stages,finish,run};
