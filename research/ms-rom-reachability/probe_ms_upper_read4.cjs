#!/usr/bin/env node
'use strict';
// Research candidate: rotate each next upper word into the existing BC
// reader. Copies: original P7 -> ordinary P1, P8 -> P6, P9 -> B, P10 -> A.
// Lower Ms is explicit scratch here; this is NOT an eight-word roundtrip.
const assert=require('node:assert/strict');
const compact=require('./probe_ms_upper_compact_exit.cjs');
const two=require('./probe_ms_two_markers.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');

function prepare(o={}) {
  const c=(o.fullUpper?require('./prepare_ms_full_upper_fixture.cjs'):
    require('./prepare_ms_upper_fixture.cjs')).prepare(o);
  if(o.initialU!==undefined) {
    // Optional negative-exponent entry fixture. This is literal input by
    // keys, never a host-read Ms value fed back to the calculator.
    inputLiteral(c,o.initialU);c.pressSequence(['X→П','9']).runFrames(8);
    push.finish(c,{phaseOffset:0});aligned(c);
  }
  return c;
}

function rotationOptions(o={},first=false) {
  const result=compact.optionsFor({...o,sourceKeys:o.pairOnly?['↔']:['F',',']});
  if(!first)result.tailActions=result.tailActions.filter(a=>a[0]!=='upper-copy-fifth');
  return result;
}

function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0},wait=o.settleFrames??8;
  for(let i=0;i<3;i++) {
    const under=label=>record('read-'+i+'/'+label);
    if((i||o.clearInitialU)&&!o.skipZeroU) {
      record('read-'+i+'/zero-source');
      c.pressSequence(['П→X','3','X→П','9']).runFrames(wait);
      push.finish(c,local,label=>record('read-'+i+'/zero-u/'+label));
    }
    compact.prepareScratch(c,local,under);
    two.finish(c,rotationOptions(local,i===0),under);
    if(i===0) {
      record('save-fifth');c.pressSequence(['П→X','8','X→П','1']).runFrames(wait);
      record('save-sixth');c.pressSequence(['П→X',',','X→П','6']).runFrames(wait);
    } else if(i===1) {
      record('save-seventh');c.pressSequence(['П→X',',','X→П','/-/']).runFrames(wait);
    }
  }
  return c;
}

function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  assert.equal(beforeRegisters[3],'000000000000');
  let stage='',seen=new Set();
  const short=new Set([0x9C,0xC9,0xD4,0xD6,0xEE,0xE7,0xA5,0xA8,0xA9,0x47,0xAC]);
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||stage.includes('/upper-')||stage.endsWith('/shifted-swap')||short.has(ip),
      otherChipsAt:()=>stage.endsWith('/upper-swap'),
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xD4,0xD6,0xE7,0xA5,0xA9,0x47].includes(e.ip)||
          [0x3A,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,before,after:fullMsPages(c),beforeRegisters,
    afterRegisters:registers(c),beforeProgram,afterProgram:program(c)};
}
const run=o=>runPrepared(prepare(o),o);
function brief(r) {
  const names=['P7','P8','P9','P10'];
  return {before:r.before,after:r.after,registers:r.afterRegisters,
    programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    copies:[1,6,11,10].map((reg,i)=>({word:names[i],reg,expected:r.before[names[i]].slice(2),actual:r.afterRegisters[reg]})),
    boundaries:r.traced.events.filter((e,i,es)=>e.ring&&(i===0||e.stage!==es[i-1].stage))
      .filter(e=>e.stage==='done'||e.stage.startsWith('save-')||e.stage.endsWith('/upper-swap')||e.stage.endsWith('/upper-after-1'))
      .map(e=>({stage:e.stage,ms:Object.fromEntries(Object.keys(r.before).map(n=>[n,two.raw(e.ring[n])]))})),
    end:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,two.raw(r.traced.events.findLast(e=>e.ring).ring[n])]))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,rotationOptions,finish,runPrepared,run,brief};
