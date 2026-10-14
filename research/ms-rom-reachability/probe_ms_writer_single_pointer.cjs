#!/usr/bin/env node
'use strict';
// Experiment: retain ordinary D instead of preparing its spare pointer.
// Only the P6 mirror is prepared. This is NOT yet a general entry contract.
const fixture=require('./prepare_ms_full_upper_fixture.cjs');
const zero=require('./probe_ms_zero_p0.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
function prepare(o={}) {
  const c=fixture.prepare({stress:true,fullUpper:['1','2','3','4'],...o});
  const keys=[...'0123456789',',','/-/','ВП','Сx','В↑'];
  for(const [value,key] of [[o.payloadD??'-1E-99','Сx'],[o.payloadE??'1.2345678E-42','В↑'],
    [o.source??'-8.7654321E-17',keys[o.sourceIndex??10]],[o.payloadP3??'-7.654321E23','3']]) {
    inputLiteral(c,value);c.pressSequence(['X→П',key]).runFrames(8);
  }
  return aligned(c);
}
function prepareScratch(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8,index=o.sourceIndex??10;
  if(![8,10,11,13,14].includes(index))throw new Error('live sources are 8/A/B/D/E; 9 and C are scratch despite belonging to the local ROM window');
  if(index===8&&!o.keepP8)throw new Error('source 8 requires keepP8');
  if(index===14&&!o.keepE)throw new Error('source E requires keepE');
  record('zero-p0');inputLiteral(c,'0');c.pressSequence(['X→П','0']).runFrames(wait);
  record('marker-p2');
  for(const key of ['Сx','K','-','ВП','K','0'])c.press(key).runFrames(12);
  c.pressSequence(['X→П','2']).runFrames(wait);
  for(let i=0;i<4;i++)c.pressSequence(['П→X','0']).runFrames(wait);
  c.pressSequence(['Сx','В↑','В↑','В↑','+']).runFrames(wait);
  for(const [value,key] of [['-1.2345678E-42','4'],['6','5'],['7','ВП'],['9','7'],...(o.keepE?[]:[['2','В↑']])]) {
    record('constant-'+key);inputLiteral(c,value);c.pressSequence(['X→П',key]).runFrames(wait);
  }
  record('normalize-p5');c.pressSequence(['K','П→X','5']).runFrames(wait);
  record('single-pointer-p6');inputLiteral(c,String(index-8));c.pressSequence(['X→П','6']).runFrames(wait);
  return c;
}
function optionsFor(o={}) {
  const result=zero.optionsFor({...o,phaseOffset:0,legacyCopy:false,directSource:false});
  result.tailActions=result.tailActions.filter(a=>!['upper-prime','upper-swap'].includes(a[0]));
  return result;
}
function finish(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0};prepareScratch(c,local,record);
  two.finish(c,optionsFor(local),record);
  return c;
}
function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  let stage='',seen=new Set();
  const short=new Set([0xAC,0xEE,0xDE,0x9C,0xC9,0xD4,0xD6,0xE7,0xA8,0xA9,0xA5,0x47]);
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||stage.startsWith('upper-')||short.has(ip),
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xA9,0xA5,0xD4,0xD6,0x47].includes(e.ip);}});
  aligned(c);return {calc:c,options:o,traced,before,after:fullMsPages(c),beforeRegisters,
    afterRegisters:registers(c),beforeProgram,afterProgram:program(c)};
}
const run=o=>runPrepared(prepare(o),o);
function brief(r) {
  const source=r.beforeRegisters[r.options.sourceIndex??10];
  return {before:r.before,after:r.after,D:[r.beforeRegisters[13],r.afterRegisters[13]],source,
    upper:r.after.P7.slice(2)===source,
    program:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    paths:r.traced.events.filter(e=>e.stage.startsWith('upper-')&&[0xD6,0xD4,0xE7].includes(e.ip))
      .map(e=>[e.stage,e.ip.toString(16),e.slot,two.raw(e.m,0),two.raw(e.r,0)]),registers:r.afterRegisters};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,prepareScratch,optionsFor,finish,runPrepared,run,brief};
