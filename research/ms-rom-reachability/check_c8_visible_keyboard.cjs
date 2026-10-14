#!/usr/bin/env node
'use strict';
// Public-display acceptance test for the keyboard C8 witness.
// Normal cases use the unchanged reference. The explicitly named causal
// control alone suppresses C8's R-lane loads; it is NOT a native witness.
const assert=require('node:assert/strict');
const {MK61}=require('./paused_keyboard_state.cjs');
const {prepareStored600,installArithmetic,prepareCombined,finishCombined}=
  require('./check_ac_signature_keyboard.cjs');
const {digest}=require('./check_c8_keyboard.cjs');

function runCase({counter=1,extraAfterKey=0,settleFrames=4,omitC8Load=false}={}) {
  const calc=new MK61(),chip=calc.ik1302;
  const press=calc.press,tick=chip.tick,microOrder=chip.executeMicroOrder;
  let activeIp=null,omittedWrites=0;
  const primitives=[],checkpoints=[];
  const record=label=>checkpoints.push({label,text:calc.displayText(),
    digits:calc.displayDigits.slice(),commas:calc.displayCommas.slice()});
  calc.press=function(...args) {
    press.apply(this,args);
    this.runFrames(extraAfterKey);
    return this;
  };
  chip.tick=function() {
    if(this.tickIndex===0) {
      activeIp=this.r[36]+16*this.r[39];
      if(activeIp===0xC7||activeIp===0xC8) primitives.push(activeIp);
    }
    return tick.call(this);
  };
  if(omitC8Load) chip.executeMicroOrder=function(n,acc) {
    if(activeIp===0xC8 && n>=15 && n<=23) {
      // C8 actually loads with order 22 at ticks 2,5,...,41, not with
      // a same-tick R assignment. Preserve command-address writes.
      const dest=(this.tickIndex+(n===22?41:n===23?40:0))%42;
      if(dest%3===1) {omittedWrites++;return;}
    }
    return microOrder.call(this,n,acc);
  };
  try {
    prepareStored600(calc);
    record('after_first_program');
    calc.inputNumber(String(counter),{clear:true}).pressSequence(['X→П','2']);
    installArithmetic(calc,{input:'1E87',multiplier:'1.0000005E4'});
    calc.pressSequence(['В/О','С/П']).runFrames(12);
    calc.pressSequence(['F','/-/']);
    calc.pressSequence(['F','ВП']).runFrames(settleFrames);
    record('after_F_PRG');
    calc.press('В↑').runFrames(settleFrames);
    record('after_ENTER');
    calc.pressSequence(['F','/-/']).runFrames(settleFrames);
    calc.pressSequence(['БП','5','8']).runFrames(settleFrames);
    calc.pressSequence(['БП','5','8']).runFrames(settleFrames);
    record('before_final_recall');
    calc.pressSequence(['П→X','7']).runFrames(8);
    record('final_wait8');
    const finalDigest=digest(calc),hitsAt8=primitives.length;
    calc.runFrames(192);
    record('final_wait200');
    return {counter,extraAfterKey,settleFrames,omitC8Load,omittedWrites,
      checkpoints,primitives,hitsAt8,finalDigest,calc};
  } finally {
    calc.press=press;
    chip.tick=tick;
    chip.executeMicroOrder=microOrder;
  }
}

function checkVisible(report) {
  const expected=['0,','00 00 00 70','0Е 00 00 71','5,        93',
    report.counter===1?'00 00 00 30':'900 00799930'];
  assert.deepEqual(report.checkpoints.map(v=>v.text),[...expected,expected.at(-1)]);
  const last=report.checkpoints.at(-1);
  assert.deepEqual(last.digits,report.counter===1?
    [15,0,0,15,0,0,15,0,0,15,3,0]:[9,0,0,15,0,0,7,9,9,9,3,0]);
  assert.ok(last.commas.every(v=>!v));
  assert.deepEqual(report.primitives,report.counter===1?[0xC8,0xC8,0xC8]:[]);
  assert.equal(report.hitsAt8,report.primitives.length);
  assert.equal(report.omittedWrites,0);
}

function run() {
  const reports=[];
  for(const spec of [{counter:1},{counter:0},
    {counter:1,extraAfterKey:1,settleFrames:60},
    {counter:1,extraAfterKey:20,settleFrames:60}]) {
    const report=runCase(spec);
    checkVisible(report);
    reports.push(report);
    console.log('PASS visible keyboard case '+JSON.stringify(spec)+': '+
      report.checkpoints.at(-1).text+'; C8 count '+report.primitives.length);
  }
  const plain=prepareCombined({counter:1});
  finishCombined(plain);
  assert.equal(reports[0].finalDigest,digest(plain));
  console.log('PASS checkpoint protocol matches the original witness exactly.');

  const causal=runCase({omitC8Load:true});
  assert.ok(causal.omittedWrites>=42,'the causal control must actually disable C8 loads');
  assert.equal(causal.omittedWrites,14*causal.primitives.length);
  assert.ok(causal.primitives.length>causal.hitsAt8,'modified body does not finish normally');
  assert.notEqual(causal.checkpoints.at(-1).text,'00 00 00 30');
  console.log('PASS artificial causal control: disabling exactly C8 data-lane loads '+
    'loses the expected terminal display and leaves repeated C8 execution. '+
    'This control is not a physical keyboard experiment.');
  return {reports,causal};
}

if(require.main===module)run();
module.exports={runCase,run};
