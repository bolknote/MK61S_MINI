#!/usr/bin/env node
'use strict';
// Candidate: false scanner alignment may store X=0 rather than W, but
// must not change Ms. Restore P0 from X1 before inspecting the display.
// Three fixed attempts cover three frame residues; convergence and data
// preservation are still obligations of native tests, not assumptions.
const buffer=require('./k1-x1-buffer-reader.cjs');
const capture=require('./k1-bank-v-capture.cjs');
const historical=require('./k1-puhov-ring-probe.cjs');
function attempt(c,o={},record=()=>{}) {
  buffer.prime(c,o,record);
  const actions=[['store',['X→П','0']],['clean',['П→X','0']],
    ['recall-original',['F','В↑']],['restore-original',['X→П','0']],['show',['↔']]];
  for(const [name,keys] of actions) {
    record('retry-'+name);c.pressSequence(keys).runFrames(8);
  }
}
function finish(c,o={},record=()=>{}) {
  const displays=[];
  for(let i=0;i<3;i++) {
    attempt(c,{...o,phaseOffset:i?0:(o.phaseOffset??0)},s=>record('attempt-'+i+'/'+s));
    record('attempt-'+i+'/display');
    const visible=c.displayText();displays.push(visible);
    if(visible==='0,')continue;
    if(!/^[0-9, +\-]+$/.test(visible)||!/[1-9]/.test(visible))
      throw new Error('Unexpected visible display: '+visible);
    return {displays,attempts:i+1};
  }
  return {displays,attempts:3};
}
const run=(o={})=>capture.run({...historical.defaults,...o},finish);
if(require.main===module)console.log(JSON.stringify(historical.brief(run(JSON.parse(process.argv[2]||'{}'))),null,2));
module.exports={attempt,finish,run};
