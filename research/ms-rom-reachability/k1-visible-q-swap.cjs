#!/usr/bin/env node
'use strict';
// Candidate clean V/Q exchange: park a disposable zero in U, keep the
// displaced W visibly, then route the request/response garbage to the
// final discarded W. No ordinary register is consumed as scratch.
// The claimed permutation must be checked natively, not inferred here.
const stack=require('./k1-visible-stack-cycle.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
function finish(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);
  const a=(s,k,n)=>stack.act(c,record,s,k,n);
  a('q-clear',['Сx','В↑','В↑','В↑','+']);
  const local={...o,phaseOffset:0};
  stack.finish(c,local,s=>record('park/'+s));
  a('q-duplicate',['В↑','В↑','В↑']);
  for(const [i,k] of ['Сx','K','Сx','K','8'].entries())a('q-marker-'+i,[k]);
  a('q-clear-x',['Сx']);
  a('q-swap',['↔']);
  a('q-clean-marker',['П→X','В↑']);
  a('q-visible-0',['F',',']);a('q-visible-1',['F',',']);
  stack.finish(c,local,s=>record('move-hole-to-v/'+s));
  stack.finish(c,local,s=>record('move-hole-to-w/'+s));
  stack.blindPush(c,local,s=>record('discard-hole/'+s));
  a('q-clear-after',['Сx','В↑','В↑','В↑','+']);
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish);
if(require.main===module) {
  const r=run(JSON.parse(process.argv[2]||'{}'));
  const stages=['q-duplicate','q-swap','q-clean-marker','move-hole-to-v/attempt-0/read-prep-0',
    'move-hole-to-w/attempt-0/read-prep-0','discard-hole/blind-duplicate','done'];
  const {raw}=require('./probe_ms_two_markers.cjs');
  console.log(JSON.stringify({before:r.before,after:r.after,registersHeld:JSON.stringify(r.beforeRegisters)===JSON.stringify(r.afterRegisters),
    programHeld:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    stages:r.traced.events.filter(e=>e.ring&&stages.includes(e.stage)&&r.traced.events.find(x=>x.stage===e.stage)===e)
      .map(e=>({stage:e.stage,words:Object.fromEntries(['X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]))}))},null,2));
}
module.exports={finish,run};
