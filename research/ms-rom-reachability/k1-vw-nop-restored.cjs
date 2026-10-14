#!/usr/bin/env node
'use strict';
// Candidate restoration of the two live stack words after removing V/W/T.
// The fixed composition must pass native timing and exit tests before use.
const nop=require('./k1-vw-nop-read.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...nop.defaults,fullUpper:['-1E-99','9022','9033','9044'],afterNop:[['K','×'],['0']]};
function finish(c,o={},record=()=>{}) {
  nop.finish(c,{...o,afterNop:[['K','×'],['0']],afterNopPhases:[0,0]},record);
  record('restore/phase');c.runFrames(o.restoreLeadPhase??0);
  stack.push(c,s=>record('restore/first/'+s));
  for(let i=0;i<2;i++)stack.act(c,record,'restore/rotate-'+i,['F',',']);
  stack.push(c,s=>record('restore/second/'+s));
  if(o.verifyExit) {
    stack.act(c,record,'post/manual',['Сx','2','В↑','3','+']);
    stack.act(c,record,'post/zero',['Сx']);
    stack.act(c,record,'post/program',['В/О','С/П'],12);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','nop/read','nop/tail-0','nop/tail-1',
    ...['first','second'].flatMap(s=>['push','push-clear','push-return'].map(t=>'restore/'+s+'/'+t)),
    'restore/rotate-0','restore/rotate-1']);
module.exports={defaults,finish,run};
