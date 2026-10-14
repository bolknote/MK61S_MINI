#!/usr/bin/env node
'use strict';
// Candidate rotation (visible X, Ms U, V, W), retaining every ordinary
// register. Unlike older readers, the W reader retains its incoming X.
// Native contracts are required; this is not a whole-domain K1 theorem.
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
const act=(c,record,stage,keys,wait=8)=>{record(stage);c.pressSequence(keys).runFrames(wait);};
function readAttempt(c,o={},record=()=>{}) {
  const a=(s,k,n)=>act(c,record,s,k,n);
  for(const [i,k] of [['П→X','0'],['П→X','0'],['F',','],['F',','],['↔']].entries())a('read-prep-'+i,k);
  for(const [i,k] of ['Сx','K','Сx','K','8'].entries())a('read-marker-'+i,[k]);
  a('read-clear',['Сx']);
  a('read-store',['X→П','0']);
  a('read-clean',['П→X','0']);
  for(let i=0;i<3;i++)a('read-return-'+i,['F',',']);
  a('read-restore',['X→П','0']);
  a('read-show',['F',',']);
}
function read(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);
  const displays=[];
  for(let i=0;i<3;i++) {
    if(i) {
      act(c,record,'read-retry-'+i+'/0',['F',',']);
      act(c,record,'read-retry-'+i+'/1',['F',',']);
    }
    readAttempt(c,o,s=>record('attempt-'+i+'/'+s));
    record('attempt-'+i+'/display');const d=c.displayText();displays.push(d);
    if(d==='0,')continue;
    if(!/^[0-9, +\-]+$/.test(d)||!/[1-9]/.test(d))throw new Error('Unexpected visible display: '+d);
    return {displays,attempts:i+1};
  }
  return {displays,attempts:3};
}
function push(c,record=()=>{}) {
  for(const [i,k] of ['Сx','K','-','ВП','K','0'].entries())act(c,record,'push-marker-'+i,[k],12);
  record('push-phase');c.runFrames(2);
  act(c,record,'push',['П→X','9']);
  act(c,record,'push-clear',['Сx']);
  act(c,record,'push-return',['+']);
}
function finish(c,o={},record=()=>{}) {
  const result=read(c,o,record);
  record('read-phase');c.runFrames((1-result.attempts%3+3)%3);
  for(const [i,k] of [['F',','],['F',','],['В↑'],['F',','],['F',',']].entries())
    act(c,record,'push-prep-'+i,k);
  push(c,record);
  return result;
}
function blindPush(c,o={},record=()=>{}) {
  // The old W must be explicitly disposable. Do not invoke on a live word.
  act(c,record,'blind-duplicate',['В↑','В↑','В↑']);
  push(c,record);
}
function probe(c,o,record) {
  act(c,record,'input',['П→X','3']);
  return finish(c,o,record);
}
const run=(o={})=>capture.run({...historical.defaults,...o},probe);
if(require.main===module)console.log(JSON.stringify(historical.brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={act,readAttempt,read,push,finish,blindPush,probe,run};
