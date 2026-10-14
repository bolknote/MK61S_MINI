#!/usr/bin/env node
'use strict';
// Candidate adaptive W placement. The ONLY live observation is the public
// display: a lone comma means another attempt, "0," means stop. Unknown
// display or three failed attempts abort; no chip/register/memory reads.
const p=require('./probe_ms_marker_clone_w.cjs');
function finish(c,o={},record=()=>{}) {
  p.finish(c,{...o,sourceKey:'В↑',sourceMirror:'6',sourceCopies:2,visibleLifts:3,
    zeroRegister:'3',payloadKey:'9',refreshSource:false,swaps:0,tailActions:[]},record);
  const displays=[];
  for(let i=0;i<3;i++) {
    record('clone-swap'+i);c.press('↔').runFrames(o.settleFrames??8);
    const display=c.displayText();displays.push(display);
    if(display==='0,')return {displays,attempts:i+1,stoppedOnVisibleZero:true};
    if(display!==',')throw new Error('Unexpected visible display; do not continue: '+JSON.stringify(display));
  }
  throw new Error('No visible zero after three attempts; do not continue.');
}
// Separate native fixture, not a hidden preparation inside live finish.
const prepare=(o={})=>p.prepare({values:['111','222','-1.2345678E-42','444'],...o});
const runPrepared=(c,o={})=>p.runPrepared(c,o,finish);
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module){const r=run(process.argv[2]?JSON.parse(process.argv[2]):{});console.log(JSON.stringify({result:r.result,...p.brief(r)},null,2));}
module.exports={prepare,finish,runPrepared,run};
