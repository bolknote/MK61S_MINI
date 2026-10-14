#!/usr/bin/env node
'use strict';
// Conditional lifetime-scheduled six-word read/restore. Read-six outputs are
// rearranged to P8=U, P1=W, P3=Q, B=fifth, A=sixth. V travels via Ms Q
// and is put back in Ms V between upper operations. No host data read drives
// execution, and there are no synchronizing getters between live stages.
const assert=require('node:assert/strict');
const reader=require('./probe_ms_read6_exit.cjs');
const one=require('./probe_ms_zero_p0.cjs');
const pair=require('./probe_ms_zero_pair.cjs');
const shifted=require('./probe_ms_shifted_swap.cjs');
const push=require('./probe_ms_p9_push.cjs');
const two=require('./probe_ms_two_markers.cjs');
const {trace,aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const prepare=o=>(o?.fullUpper?require('./prepare_ms_full_upper_fixture.cjs'):reader).prepare(o);

function recoverV(c,o={},record=()=>{}) {
  const wait=o.settleFrames??8;
  record('save-q-backup');c.pressSequence(['П→X','3','X→П','В↑']).runFrames(wait);
  record('zero-p3');inputLiteral(c,'0');c.pressSequence(['X→П','3']).runFrames(wait);
  shifted.finish(c,{...o,phaseOffset:0,lifts:3,save:false},label=>record('exchange-wq/'+label));
  // The last secondary X/Y output can overlap the first zero lift. After
  // two lifts Y/Z therefore vary, but T retains the source in both observed
  // interleavings. Three ordinary left rotations select T; one selects Y.
  shifted.finish(c,{...o,phaseOffset:0,lifts:2,
    postSwap:[['П→X','3'],['П→X','3'],...Array.from({length:o.legacyBridgeReturn?1:3},()=>['F',','])],save:true},
    label=>record('read-q/'+label));
  record('recovered-v');
  if(o.finalRestore) {
    for(const [source,destination] of [['8','4'],['9','5'],['1','6'],['В↑','7']]) {
      record('final-copy-'+source+'-'+destination);
      c.pressSequence(['П→X',source,'X→П',destination]).runFrames(wait);
    }
    for(const source of ['7','6','5','4']) {
      record('restore-source-'+source);c.pressSequence(['П→X',source,'X→П','9']).runFrames(wait);
      push.finish(c,{...o,phaseOffset:0},label=>record('restore-'+source+'/'+label));
    }
  } else {
    push.finish(c,{...o,phaseOffset:0},label=>record('put-v-in-u/'+label));
    record('zero-source');c.pressSequence(['П→X','0','X→П','9']).runFrames(wait);
    push.finish(c,{...o,phaseOffset:0},label=>record('move-v-to-v/'+label));
    record('restore-q-backup');c.pressSequence(['П→X','В↑','X→П','3']).runFrames(wait);
  }
  return c;
}

function finish(c,o={},record=()=>{}) {
  assert.ok([0,1,2].includes(o.phaseOffset??0));c.runFrames(o.phaseOffset??0);
  const local={...o,phaseOffset:0,keepP8:true,sourceIndex:10,directSource:false,legacyCopy:false},wait=o.settleFrames??8;
  const under=name=>label=>record(name+'/'+label);
  reader.finish(c,{...o,phaseOffset:0,restoreLower:true,zeroRegister:'3',keepP8:false},under('read-six'));
  for(const [source,destination] of [['8','9'],['1','8'],['/-/','1'],['Сx','3'],['9','/-/']]) {
    record('relocate-'+source+'-'+destination);
    c.pressSequence(['П→X',source,'X→П',destination]).runFrames(wait);
  }
  one.prepareScratch(c,local,under('sixth-to-top'));
  one.finish(c,local,under('sixth-to-top'));
  if(!o.skipBridges)recoverV(c,local,under('bridge-first'));
  one.prepareScratch(c,local,under('sixth-to-second'));
  two.finish(c,pair.moveOptions(local),under('sixth-to-second'));
  if(!o.skipBridges)recoverV(c,local,under('bridge-second'));
  const last={...local,sourceIndex:11};
  one.prepareScratch(c,last,under('fifth-to-top'));
  one.finish(c,last,under('fifth-to-top'));
  recoverV(c,{...local,finalRestore:true},under('restore-all-lower'));
  return c;
}

function runPrepared(c,o={}) {
  const before=fullMsPages(c),beforeRegisters=registers(c),beforeProgram=program(c);
  assert.equal(beforeRegisters[3],'000000000000');
  let stage='',seen=new Set();
  const short=new Set([0xAC,0xEE,0xDE,0x9C,0xC9,0xD4,0xD6,0xA2,0xA3,0xE5,0xE6,0xE8,0xA7,0xE7,0xA8,0xA9,0xA5,0x47]);
  const traced=trace(c,calc=>{finish(calc,o,label=>{stage=label;});stage='done';calc.runFrames(3);},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      eventFilter:ip=>stage==='done'||stage.includes('/upper-')||stage.endsWith('/shifted-swap')||stage.includes('/post-swap-')||short.has(ip),
      otherChipsAt:()=>stage.endsWith('/upper-swap')||stage.includes('/shifted-swap')||stage.includes('/post-swap-'),
      ringAt:e=>{e.stage=stage;const first=!seen.has(stage);seen.add(stage);
        return first||[0xEE,0xE7,0xA9,0xA5,0xD4,0xD6,0x47].includes(e.ip)||
          [0x3A,0x4E,0x2A,0x39].includes(e.otherChips?.[4].ip);}});
  aligned(c);return {calc:c,options:o,traced,before,after:fullMsPages(c),beforeRegisters,
    afterRegisters:registers(c),beforeProgram,afterProgram:program(c)};
}
const run=o=>runPrepared(prepare(o),o);
function brief(r) {
  const names=['U','V','W','Q','P7','P8','P9','P10'];
  const boundaries=['relocate-8-9','bridge-first/save-q-backup','bridge-first/put-v-in-u/clear-before',
    'sixth-to-second/zero-p0','bridge-second/save-q-backup','bridge-second/put-v-in-u/clear-before',
    'fifth-to-top/zero-p0','restore-all-lower/save-q-backup','restore-all-lower/final-copy-8-4','done'];
  return {before:r.before,after:r.after,restored:JSON.stringify(r.before)===JSON.stringify(r.after),
    registers:r.afterRegisters,programPreserved:JSON.stringify(r.beforeProgram)===JSON.stringify(r.afterProgram),
    boundaries:boundaries.map(stage=>{const e=r.traced.events.find(e=>e.stage===stage&&e.ring);return e&&{stage,
      ms:Object.fromEntries(names.map(n=>[n,two.raw(e.ring[n])])),
      copies:Object.fromEntries([['U','P0'],['V','P1'],['Q','P3'],['marker','P8'],['control','P9'],['X1','A'],['X','B'],['T','E']].map(([n,k])=>[k,two.raw(e.ring[n],0)]))};}),
    end:Object.fromEntries(['X','Y','Z','T'].map(n=>[n,two.raw(r.traced.events.findLast(e=>e.ring).ring[n])]))};
}
if(require.main===module)console.log(JSON.stringify(brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare,recoverV,finish,runPrepared,run,brief};
