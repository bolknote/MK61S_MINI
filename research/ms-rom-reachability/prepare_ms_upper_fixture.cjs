'use strict';
// Separate, native test-data preparation. It deliberately uses an old
// destructive readout to populate nonzero Ms P7/P8, then fixes U/V/W/Q.
const assert=require('node:assert/strict');
const marker=require('./probe_a8_marker_route.cjs');
const readout=require('./probe_a8_ms_readout.cjs');
const push=require('./probe_ms_p9_push.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages,inputLiteral}=require('./probe_c8_payload.cjs');
const {program}=require('./probe_a8_ms_readout.cjs');
function prepare({values=['111','222','333','444'],upperValues=['111','222','333','444'],stress=false}={}) {
  const options={values:upperValues,seedLowDigit:0,clearKey:'8',markerLifts:1,
    captureProgram:false,markerLift:'recall-zero',autoRecovery:false};
  const calc=marker.prepare(options);
  for(let i=0;i<2;i++) {
    marker.finish(calc,options);readout.recover(calc,options);calc.runFrames(3);aligned(calc);
  }
  const upper=fullMsPages(calc);
  for(let i=0;i<4;i++) {
    inputLiteral(calc,values[3-i]);calc.pressSequence(['X→П',String(4+i)]);
  }
  push.fill4FromRegisters(calc);aligned(calc);
  for(const name of ['P7','P8','P9','P10']) assert.equal(fullMsPages(calc)[name],upper[name]);
  // Outputs are re-seeded: a test cannot pass by finding fixture leftovers.
  const keys=[...'0123456789',',','/-/','ВП','Сx','В↑'];
  for(let i=0;i<(stress?15:10);i++)if(i!==3) {
    inputLiteral(calc,String(101+i));calc.pressSequence(['X→П',keys[i]]);
  }
  calc.pressSequence(['В/О','F','ВП','2','В↑','3','+','С/П','K','0','F','/-/','В/О']);
  assert.deepEqual(program(calc).slice(0,6),[2,0x0E,3,0x10,0x50,0x54]);
  return aligned(calc);
}
module.exports={prepare};
