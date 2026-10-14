#!/usr/bin/env node
'use strict';
// Research candidate: preserve the original M1 P0 in visible X/Y while
// writing the old Ms V into P0. A subsequent V write is still required.
// Unlike older readers, the live prefix neither reads nor reserves P3.
const fixture=require('./probe_ms_classic_v.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {inputLiteral,fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
function prepare(o={}) {
  const c=o.fullUpper?require('./prepare_ms_full_upper_fixture.cjs').prepare({stress:true,...o}):fixture.prepare({stress:true,...o});
  for(const [value,key] of [[o.incoming??'101','0'],[o.p3??'777','3']]) {
    inputLiteral(c,value);c.pressSequence(['X→П',key]).runFrames(8);
  }
  // Test fixture only, before the protocol and before any "before" snapshot.
  // Native keystrokes preserve the no-setter contract. Protocol controllers
  // must not read these chosen initial values or use them as an external bank.
  const registerKeys=[...'0123456789',',','/-/','ВП','Сx','В↑'];
  for(const [index,value] of Object.entries(o.fixtureRegisters??{})) {
    const i=Number(index);
    if(!Number.isInteger(i)||i<0||i>=registerKeys.length)throw new Error('bad fixture register '+index);
    inputLiteral(c,String(value));c.pressSequence(['X→П',registerKeys[i]]).runFrames(8);
  }
  return aligned(c);
}
function finish(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);const wait=o.settleFrames??8;
  const act=(name,keys,frames=wait)=>{record(name);c.pressSequence(keys).runFrames(frames);};
  act('clear',['Сx','В↑','В↑','В↑','+']);
  for(const [i,key] of ['Сx','K','-','ВП','K','0'].entries())act('marker-'+i,[key],o.markerFrames??12);
  act('load-0a',['П→X','0']);act('load-0b',['П→X','0']);act('store-0',['X→П','0']);
  for(const [i,keys] of (o.tail??[]).entries())act('tail-'+i,keys);
  return c;
}
function run(o={},operation=finish,otherChipStages=[]) {
  const calc=prepare(o),before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  aligned(calc);let stage='',seen=new Set();
  const selected=new Set([0x9C,0xEE,0xE7,0xE9,0xA8,0xA9,0xA3,0x47,0xD4,0xD6,0xDD,0xA5,0xA7,0xAC,0xC7,0xC8,0xC9]);
  const secondaryStages=new Set(otherChipStages);
  const traced=trace(calc,c=>{operation(c,o,s=>{stage=s;});stage='done';c.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>secondaryStages.has(stage)||!seen.has(stage)||selected.has(ip),
      otherChipsAt:()=>secondaryStages.has(stage),
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xE7,0xE9,0xA8,0xD4,0xA5,0x47,0xA9].includes(e.ip);}});
  aligned(calc);
  return {options:o,calc,before,beforeRegisters,beforeProgram,traced,
    after:fullMsPages(calc),afterRegisters:registers(calc),afterProgram:program(calc)};
}
function brief(r) {
  const end=r.traced.events.find(e=>e.stage==='done'&&e.ring);
  return {options:r.options,before:r.before,after:r.after,
    beforeRegisters:r.beforeRegisters,afterRegisters:r.afterRegisters,
    visible:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,raw(end.ring[n])])),
    programHeld:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    stages:r.traced.events.filter(e=>e.ring&&r.traced.events.find(x=>x.stage===e.stage)===e)
      .map(e=>({stage:e.stage,words:Object.fromEntries(['X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]))})),
    paths:r.traced.events.filter(e=>e.stage==='store-0'||e.stage.startsWith('tail-'))
      .filter(e=>[0xEE,0xE7,0xE9,0xD4,0xD6].includes(e.ip))
      .map(e=>[e.stage,e.command,e.ip.toString(16),e.slot,e.raw,raw(e.r,0)])};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,finish,run,brief};
