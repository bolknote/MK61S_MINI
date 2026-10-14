#!/usr/bin/env node
'use strict';
// Structural candidate only: clear the old marker, make P0 disposable,
// then back q/u in Y/Z before a new logical marker and V-directed E9.
// Native preservation and cleanup are not assumed by this probe.
const repack=require('./k1-visible-marker-repack.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const brief=require('./k1-v-marker-probe.cjs').brief;
const defaults={...repack.defaults,clonePhase:1,
  values:['-1.2345678E-42','-7.654321E-23','-9.8765432E-17','-12345678']};
function finish(c,o={},record=()=>{}) {
  repack.finish(c,{...o,after:[['П→X','0'],['0'],['X→П','0'],['П→X','0']]},s=>record('entry/'+s));
  for(let i=0;i<3;i++)stack.act(c,record,'w-to-x-'+i,['F',',']);
  stack.act(c,record,'save-w',['X→П','0']);
  for(let i=0;i<3;i++)stack.act(c,record,'u-to-x-'+i,['F',',']);
  const read=stack.read(c,{...o,phaseOffset:0},s=>record('read-q/'+s));
  record('read-q/phase');c.runFrames((1-read.attempts%3+3)%3);
  for(let i=0;i<2;i++)stack.act(c,record,'payload-rotate-'+i,['F',',']);
  stack.act(c,record,'payload-swap',['↔']);
  for(const [i,k] of ['Сx','K','Сx','K','8'].entries())stack.act(c,record,'marker-'+i,[k]);
  stack.act(c,record,'clone-prefix',o.clonePrefix??['K']);
  record('clone-phase');c.runFrames(o.clonePhase??0);
  stack.act(c,record,'clone-sign',o.cloneKeys??['5']);
  if(o.afterClonePhase){record('after-clone-phase');c.runFrames(o.afterClonePhase);}
  for(const [i,keys] of (o.afterClone??[]).entries())
    stack.act(c,record,'after-clone-'+i,keys,o.afterCloneWaits?.[i]??8);
}
function run(o={}) {
  o={...defaults,...o};return cap.run(o,finish,['clone-prefix','clone-sign',
    ...(o.afterClone??[]).map((_,i)=>'after-clone-'+i)]);
}
if(require.main===module) {
  const r=run(JSON.parse(process.argv[2]||'{}')),b=brief(r);
  b.rows=b.rows.filter(e=>e.stage==='save-w'||e.stage==='payload-rotate-0'||
    e.stage.startsWith('marker-')||e.stage.startsWith('clone')||e.stage.startsWith('after-clone')||
    e.stage==='done'||e.missing.length);
  b.routes=b.routes.filter(e=>e.stage.startsWith('clone')||e.stage.startsWith('after-clone'));
  console.log(JSON.stringify(b,null,2));
}
module.exports={defaults,finish,run};
