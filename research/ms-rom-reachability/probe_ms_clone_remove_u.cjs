#!/usr/bin/env node
'use strict';
// Native candidate: combine W cloning with formatter-based U removal.
// Only the public display controls stopping; this does not clear visible
// X/Y markers, restore lower Ms, or implement a full upper exchange.
const base=require('./probe_ms_clone_tail_t.cjs');
const clone=require('./probe_ms_marker_clone_w.cjs');
const guard='-1.2345678E-42',displayGuard='-1,2345678-42';
function finish(c,o={},record=()=>{}) {
  base.finish(c,{...o,tailValue:guard,swaps:0},record);
  const displays=[];
  for(let i=0;i<3;i++) {
    record('clone-swap-'+i);c.press('↔').runFrames(o.settleFrames??8);
    const display=c.displayText();displays.push(display);
    if(display===displayGuard)return {displays,attempts:i+1,stoppedOnGuard:true};
    if(display!==',')throw new Error('Unexpected visible display; stop: '+JSON.stringify(display));
  }
  throw new Error('No guard display after three attempts; stop.');
}
const prepare=base.prepare;
const runPrepared=(c,o={})=>clone.runPrepared(c,o,finish);
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module){const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});console.log(JSON.stringify({...base.brief(r),result:r.result},null,2));}
module.exports={prepare,finish,runPrepared,run,guard,displayGuard};
