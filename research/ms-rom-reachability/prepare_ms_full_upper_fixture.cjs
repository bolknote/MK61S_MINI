'use strict';
// Native-only fixture with four explicitly selected upper Ms words.
// Two upper-stack pushes move the old nonzero pair into P9/P10, then the
// established lower writer restores the independent lower fixture values.
const assert=require('node:assert/strict');
const base=require('./prepare_ms_upper_fixture.cjs');
const one=require('./probe_ms_upper_write1.cjs');
const two=require('./probe_ms_two_markers.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const names=['P7','P8','P9','P10'];
function pushOptions(o={}) {
  const result=one.optionsFor({...o,phaseOffset:0});
  result.tailActions=result.tailActions.filter(a=>!['upper-prime','upper-swap'].includes(a[0]));
  return result;
}
function prepare(o={}) {
  const words=o.fullUpper;assert.ok(Array.isArray(words)&&words.length===4);
  const values=o.values??['111','222','333','444'];
  const c=base.prepare({...o,upperValues:[words[3],words[2],'333','444']});
  const code=program(c);
  for(const word of [words[1],words[0]]) {
    one.prepareScratch(c,{phaseOffset:0});inputLiteral(c,word);c.pressSequence(['X→П',',']);aligned(c);
    const before=fullMsPages(c),source=registers(c)[10];
    two.finish(c,pushOptions());c.runFrames(3);aligned(c);
    const after=fullMsPages(c);
    for(let i=0;i<4;i++)assert.equal(after[names[i]],before[names[i]].slice(0,2)+(i?before[names[i-1]].slice(2):source),
      'native fixture upper push: '+names[i]);
    assert.deepEqual(program(c),code);
  }
  const upper=fullMsPages(c);
  for(let i=0;i<4;i++){inputLiteral(c,values[3-i]);c.pressSequence(['X→П',String(4+i)]);}
  push.fill4FromRegisters(c);aligned(c);
  for(const n of names)assert.equal(fullMsPages(c)[n],upper[n]);
  const keys=[...'0123456789',',','/-/','ВП','Сx','В↑'];
  for(let i=0;i<(o.stress?15:10);i++)if(i!==3){inputLiteral(c,String(101+i));c.pressSequence(['X→П',keys[i]]);}
  aligned(c);assert.deepEqual(program(c),code);return c;
}
module.exports={prepare,pushOptions};
