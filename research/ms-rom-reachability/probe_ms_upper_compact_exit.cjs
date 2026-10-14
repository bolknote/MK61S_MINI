#!/usr/bin/env node
'use strict';
// Conditional compact guarded upper-two reader with a tested exit. Native keys only.
// BC with decimal pointer 10 saves the sixth word in A; the same pointer
// pair then makes DC read ordinary P3=0. This frees P1/P6/B/D for backups.
// Ms is NOT restored. In particular a later formatter may replace P7 too.
const fixture=require('./prepare_ms_upper_fixture.cjs');
const upper=require('./probe_ms_upper_swap.cjs');
const indirect=require('./probe_ms_upper_indirect.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const loadC=['K','П→X','ВП'],loadE=['K','П→X','В↑'];
const clear=['Сx','В↑','В↑','В↑','+'];
function prepareScratch(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8;
  record('compact-payload-marker');
  for(const key of ['Сx','K','-','ВП','K','0'])c.press(key).runFrames(12);
  c.pressSequence(['X→П','2']).runFrames(wait);
  for(let i=0;i<4;i++)c.pressSequence(['П→X','3']).runFrames(wait);
  c.pressSequence(clear).runFrames(wait);
  for(const [value,key] of [[o.postPointer??'111','0'],['-1.2345678E-42','4'],[o.canonicalCaptureMirror?'10':'9','5'],
    ['10','ВП'],['9','7'],['2','В↑']]) {
    record('compact-constant-'+key);
    inputLiteral(c,value);c.pressSequence(['X→П',key]).runFrames(wait);
  }
  if(!o.canonicalCaptureMirror) {
    // Index 5 increments 9 to 10 and stores its normalized representation.
    // C stays canonical 10: its six normalization passes are significant.
    record('compact-normalize-p5');c.pressSequence(['K','П→X','5']).runFrames(wait);
  }
  return c;
}
function optionsFor(o={}) {
  const result=upper.optionsFor(indirect.optionsFor({...o,pointer:'10',fifthCopyKey:'8',
    beforeSwapKeys:['П→X','4'],traceFormatterExit:true,
    afterKeys:[loadC,loadC,loadC,loadE,loadC,['П→X','4'],['П→X','3'],['П→X','3'],clear]}));
  // The redundant original store to P0 would destroy the late pointer 111.
  // upper-copy-fifth saves the fifth word directly in ordinary P8 instead.
  result.reads=false;
  return result;
}
const prepare=(o={})=>aligned(prepareScratch(fixture.prepare(o),o));
const finish=(c,o={},record=()=>{})=>two.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>two.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
if(require.main===module)console.log(JSON.stringify(upper.brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepareScratch,prepare,finish,runPrepared,run,optionsFor};
