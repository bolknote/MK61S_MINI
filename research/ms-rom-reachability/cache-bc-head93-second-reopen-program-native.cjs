#!/usr/bin/env node
'use strict';
// Device-derived fixed programme XY/STOP instead of the manual XY tail.
// Install only by PRGM/public keys in canonical geometry. Fresh guarded
// originals/full mirrors; no ROM/state/setter/phase imports or feedback.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-t-packet-prepare-native.cjs');
const FIRST='007012345678',SECOND='007024681357';
function run({proof=false}={}) {
  const v=prepare({proof,phase:'yku',secondPhase:'p8-reopen-run-stop'});
  const get=n=>v.exitStages.find(s=>s.name===n);
  const ready=get('packet-normal-preclear4'),installed=get('packet-program-auto'),before=get('packet-reopen-control-front3');
  const final=v.exitStages.at(-1);
  assert.equal(ready.words['Ms:P8'],SECOND);assert.equal(ready.words['Ms:P10'],FIRST);
  const programmed=installed.program.slice(0,4);
  const expectedProgram=installed.program[0]===0x14&&installed.program[1]===0x50;
  assert.equal(expectedProgram,true,'must actually install XY/STOP before interpreting the run');
  assert.deepEqual(installed.program.flatMap((x,j)=>x===ready.program[j]?[]:[j]),[0,1]);
  assert.deepEqual(before.program,installed.program);
  assert.equal(before.words['Ms:P8'],SECOND);assert.equal(before.words['Ms:P10'],FIRST);
  assert.ok(!before.registers.includes(FIRST)&&!before.registers.includes(SECOND));
  assert.equal(v.report.packetAudit.numberHeld,false);
  assert.deepEqual(v.report.packetAudit.firstDifference,{word:2957605,
    stage:'packet-program-run',moment:'after',actual:'FFF000000000'});
  assert.notEqual(final.registers[6],SECOND);
  return {...v,programDiagnostic:{programmed,expectedProgram,
    changedProgram:installed.program.flatMap((x,j)=>x===ready.program[j]?[]:[j]),
    ready:get('packet-program-auto'),beforeRun:get('packet-program-run-home'),
    programmeEnd:get('packet-program-run'),output:get('packet-program-output'),
    firstHeld:v.report.packetAudit.numberHeld,
    firstFailure:v.report.packetAudit.firstDifference,
    final:{display:final.display,words:final.words,registers:final.registers,pc:final.pc},
    success:false,
    boundary:'measured FAILED fixed XY/STOP programme: installed bytes correct, but FIRST/P10 is lost; NOT a reverse reader/full K1/K2'}};
}
if(require.main===module) {
  const v=run({proof:process.argv.includes('--proof-input')});
  const d=v.programDiagnostic;
  console.log(JSON.stringify(process.argv.includes('--proof-input')?v:{
    programmed:d.programmed,expectedProgram:d.expectedProgram,changedAtInstallation:d.changedProgram,
    changedDuringRun:d.programmeEnd.program.flatMap((x,j)=>x===d.ready.program[j]?[]:[j]),
    before:{pc:d.beforeRun.pc,P8:d.beforeRun.words['Ms:P8'],P10:d.beforeRun.words['Ms:P10'],markers:d.beforeRun.markers},
    after:{pc:d.final.pc,display:d.final.display,R6:d.final.registers[6],
      P7:d.final.words['Ms:P7'],P8:d.final.words['Ms:P8'],P10:d.final.words['Ms:P10']},
    firstHeld:d.firstHeld,firstFailure:d.firstFailure,success:d.success,boundary:d.boundary}));
}
module.exports={run};
