#!/usr/bin/env node
'use strict';
// Diagnostic only: exactly two uninterrupted keyboard invocations.
// No reset, imported state, getter alignment, or extra idle frames between
// invocations. The optional manual/program demonstrations are excluded.
const restored=require('./k1-vw-nop-restored.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const defaults={...restored.defaults,verifyExit:false};
function finish(c,o={},record=()=>{}) {
  for(let i=0;i<2;i++) {
    record('repeat/'+i+'/start');
    restored.finish(c,{...o,verifyExit:false},s=>record('repeat/'+i+'/'+s));
    record('repeat/'+i+'/end');
  }
}
function run(o={}) {
  let failure=null;
  const wrapped={defaults,finish(c,options,record) {
    try {finish(c,options,record);}
    catch(error) {
      // Preserve already observed boundaries if a display-only reader
      // rejects this continuous input. This is an explicit failed run.
      failure={name:error.name,message:error.message};
      record('repeat/aborted');
    }
  }};
  return {...frame.run(wrapped,o),failure};
}
module.exports={defaults,finish,run};
