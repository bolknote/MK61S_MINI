#!/usr/bin/env node
'use strict';
// Closed Y/T/V exit on the audited fixtures: RCL0 replaces LastX, a binary drop
// duplicates the endangered v, and the final rotation removes the marker.
// The following reader and two lower pushes return v to stored memory.
const deep=require('./k1-z-backed-deep-entry.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...deep.defaults,
  deepTail:[['K','0'],['П→X','0'],['F',','],['K','0'],['В↑'],['-'],['F',',']],
  deepTailPhases:[1,1,0,0,1,1,0],readerLeadPhase:1};
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};deep.finish(c,o,record);
  if(o.stopAfterClear)return;
  record('return/reader-phase');c.runFrames(o.readerLeadPhase);
  for(let i=0;i<2;i++)stack.act(c,record,'return/v-to-x-'+i,['F',',']);
  const read=stack.read(c,{...o,phaseOffset:0},s=>record('return/read-q/'+s));
  record('return/read-phase');c.runFrames((1-read.attempts%3+3)%3);
  stack.act(c,record,'return/save-q',['X→П','0']);
  stack.push(c,s=>record('return/first/'+s));
  for(let i=0;i<2;i++)stack.act(c,record,'return/v-to-t-'+i,['F',',']);
  stack.push(c,s=>record('return/second/'+s));
  if(o.verifyExit) {
    stack.act(c,record,'post/manual',['Сx','2','В↑','3','+']);
    stack.act(c,record,'post/zero',['Сx']);
    stack.act(c,record,'post/program',['В/О','С/П'],12);
  }
}
const run=(o={})=>frame.run({defaults,finish},o);
const traced=(o={})=>{
  o={...defaults,...o};
  return cap.run(o,finish,['clone-prefix','clone-sign','after-clone-0','rotate/reserve','rotate/tail-0',
    'deep/prepare','deep/clone',...[0,1,2,3,4].map(i=>'deep/marker-'+i),
    ...o.deepTail.map((_,i)=>'deep/tail-'+i),
    ...['first','second'].flatMap(s=>['push','push-clear','push-return'].map(t=>'return/'+s+'/'+t))]);
};
if(require.main===module) {
  const r=run({verifyExit:true,...JSON.parse(process.env.K1_YTV_CLOSED_OPTIONS||'{}')});
  console.log(JSON.stringify({options:r.options,lost:r.rows.filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),
    rows:r.rows.filter(x=>x.stage==='return/reader-phase'||x.stage==='return/save-q'||
      x.stage.startsWith('post/')||x.stage==='immediate'||x.stage==='done')
      .map(({stage,phase,values,registers})=>({stage,phase,values,p0:registers[0]}))},null,2));
}
module.exports={defaults,finish,run,traced};
