#!/usr/bin/env node
'use strict';
// Research: P0 serves as both the zero source and the late pointer zero.
// C=7 / normalized P5=7 select ordinary P0 through the V-relative M1 base.
// P3 is payload, never a zero or a pointer in this variant.
const fixture=require('./prepare_ms_upper_fixture.cjs');
const one=require('./probe_ms_upper_write1.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {inputLiteral}=require('./probe_c8_payload.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const clear=['Сx','В↑','В↑','В↑','+'];
function prepareScratch(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8;
  record('zero-p0');inputLiteral(c,'0');c.pressSequence(['X→П','0']).runFrames(wait);
  record('marker-p2');
  for(const key of ['Сx','K','-','ВП','K','0'])c.press(key).runFrames(12);
  c.pressSequence(['X→П','2']).runFrames(wait);
  for(let i=0;i<4;i++)c.pressSequence(['П→X','0']).runFrames(wait);
  c.pressSequence(clear).runFrames(wait);
  for(const [value,key] of [['-1.2345678E-42','4'],['6','5'],['7','ВП'],['9','7'],['2','В↑']]) {
    record('constant-'+key);inputLiteral(c,value);c.pressSequence(['X→П',key]).runFrames(wait);
  }
  record('normalize-p5');c.pressSequence(['K','П→X','5']).runFrames(wait);
  if(!o.directSource) {
    record('writer-pointers');
    if((o.sourceIndex??10)===10)one.preparePointers(c);
    else {
      if(o.sourceIndex!==11)throw new Error('Only the derived A/B source pair is supported');
      inputLiteral(c,'11');c.pressSequence(['X→П','Сx','K','П→X','Сx']);
      inputLiteral(c,'3');c.pressSequence(['X→П','6']);
    }
  }
  return c;
}
function prepare(o={}) {
  const c=(o.fullUpper?require('./prepare_ms_full_upper_fixture.cjs'):fixture).prepare(o);
  for(const [value,key] of [[o.source??'-8.7654321E-17',o.sourceIndex===11?'/-/':','],[o.payload??'-7.654321E23','3'],
    ...(o.keepP8?[[o.p8Payload??'12345678','8']]:[]),
    ...(o.directSource?[['-1E-99','6'],['1.2345678E99','Сx']]:[])]) {
    inputLiteral(c,value);c.pressSequence(['X→П',key]);
  }
  return aligned(prepareScratch(c,o));
}
function optionsFor(o={}) {
  const result=one.optionsFor({...o,zeroRegister:'0'});
  for(const a of result.tailActions)if(a[1].length===2&&a[1][0]==='П→X'&&a[1][1]==='3')a[1]=['П→X','0'];
  if(o.directSource)result.tailActions.find(a=>a[0]==='upper-after-0')[1]=['П→X',','];
  return result;
}
const finish=(c,o={},record=()=>{})=>two.finish(c,optionsFor(o),record);
const runPrepared=(c,o={})=>two.runPrepared(c,optionsFor(o));
const run=(o={})=>runPrepared(prepare(o),o);
function brief(r) {
  return {before:r.before,after:r.after,registers:r.afterRegisters,
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    paths:r.traced.events.filter(e=>e.stage.startsWith('upper-after-')&&[0xD6,0xD4,0xE7].includes(e.ip))
      .map(e=>[e.stage,e.ip.toString(16),e.slot,two.raw(e.m,0),two.raw(e.r,0),e.nextIp.toString(16)]),
    end:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,two.raw(r.traced.events.findLast(e=>e.ring).ring[n])]))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepareScratch,prepare,optionsFor,finish,runPrepared,run,brief};
