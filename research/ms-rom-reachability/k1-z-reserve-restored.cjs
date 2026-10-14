#!/usr/bin/env node
'use strict';
// Candidate exit from the real/Z reserve: rotate away the visible marker,
// then rescue the displaced v before using the ordinary lower push twice.
const reserve=require('./k1-y-t-rotate-reserve.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...reserve.defaults};
function finish(c,o={},record=()=>{}) {
  reserve.finish(c,{...o,afterReserve:[['F',',']],afterReservePhases:[],afterReserveWaits:[]},record);
  if(o.stopAfterUnmark)return;
  for(let i=0;i<3;i++)stack.act(c,record,'z-exit/v-to-x-'+i,['F',',']);
  const read=stack.read(c,{...o,phaseOffset:0},s=>record('z-exit/read-q/'+s));
  record('z-exit/read-phase');c.runFrames((1-read.attempts%3+3)%3);
  stack.act(c,record,'z-exit/save-q',['X→П','0']);
  stack.push(c,s=>record('z-exit/first/'+s));
  for(let i=0;i<2;i++)stack.act(c,record,'z-exit/v-to-t-'+i,['F',',']);
  stack.push(c,s=>record('z-exit/second/'+s));
  if(o.verifyExit) {
    stack.act(c,record,'post/manual',['Сx','2','В↑','3','+']);
    stack.act(c,record,'post/zero',['Сx']);
    stack.act(c,record,'post/program',['В/О','С/П'],12);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0','rotate/reserve','rotate/tail-0',
    ...['first','second'].flatMap(s=>['push','push-clear','push-return'].map(t=>'z-exit/'+s+'/'+t))]);
module.exports={defaults,finish,run};
