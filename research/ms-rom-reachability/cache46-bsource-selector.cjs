#!/usr/bin/env node
'use strict';
// Native preparation of the header9 source, NOT a native writer entry.
// Only fixed keys/frames; all observers passive; fresh complete mirrors.
const assert=require('node:assert/strict');
const {run,prepareSelector,finishSelector}=require('./st34-origin-trace.cjs');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const {machineSnapshot}=require('./probe_c8_pc_reader.cjs');
const {fixtures,install}=require('./check_partial_k2_program_scan.cjs');
const positions=[0,3,9,12,18,21],keys=['F','Сx',','];
const lane=(e,n)=>Array.from({length:12},(_,j)=>e.r[n+3*j]);

function check(options={}, {mirror=true,log=true}={}) {
  const settings={...options,selector:9},observed=run(settings),calc=observed.calc;
  const payload=positions.map(j=>calc.ik1302.r[j]);
  assert.deepEqual(payload,[3,10,4,13,5,11]);
  assert.deepEqual(calc.ik1302.stack.slice(33,36),[9,15,5]);
  const readerInitial=machineSnapshot(calc).ik1302;
  const ms=fullMsPages(calc),program=Array.from({length:105},(_,j)=>calc.readCommand(j));
  const result=trace(calc,c=>{c.pressSequence(keys);aligned(c);},{
    extraIps:Array.from({length:256},(_,j)=>j),fullState:true,allWrites:true,
  });
  const dc=result.events.find(e=>e.ip===0xDC);
  assert.ok(dc);
  assert.deepEqual(positions.map(j=>dc.r[j]),payload);
  assert.deepEqual(lane(dc,0),[3,10,15,4,13,15,5,11,15,10,9,9]);
  assert.equal(dc.st[22],0,'native source for the proven BE-to-B0 exit');
  assert.equal(dc.r[34],15,'writer control is STILL F in B, not9');
  assert.notDeepEqual(positions.map(j=>dc.r[j+1]),payload,
    'native cache is still in A, not the required B source');
  assert.ok(!result.events.some(e=>e.command<=dc.command&&e.ip===0xEE));
  assert.deepEqual(result.writes.filter(e=>e.chip===3&&e.command<dc.command),[]);
  assert.deepEqual(fullMsPages(calc),ms,'all56 Ms bytes unchanged, not a cache store');
  assert.deepEqual(Array.from({length:105},(_,j)=>calc.readCommand(j)),program);

  if(mirror) {
    const plain=new MK61();
    for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
      plain[name]=()=>{throw Error('Forbidden state setter: '+name);};
    install(plain,fixtures[1]);preparePayload('8.7654321E-91',plain);
    prepareSelector(plain,settings);finishSelector(plain,settings);aligned(plain);
    plain.pressSequence(keys);aligned(plain);
    assert.deepEqual(machineSnapshot(plain),machineSnapshot(calc),
      'complete fresh unobserved machine uses only the same keys and fixed waits');
  }
  const report={options,selector:9,rawThreeBytes:[0xA3,0xD4,0xB5],
    cacheLaneAtDC:'A',sourceTagAtDC:lane(dc,0).slice(9),ST22:dc.st[22],
    actualBHeader:dc.r[34],all56MsBytesHeld:true,programHeld:true,
    observerIndependent:mirror,nativeBSourceWriterEntry:false,partialK2:false};
  if(log)console.log(JSON.stringify(report));
  return {report,dc,readerInitial};
}

if(require.main===module) {
  if(process.argv.includes('--proof-input'))
    console.log(JSON.stringify(check({}, {mirror:false,log:false})));
  else {
    check();check({phaseOffset:2,settleFrames:10});
    console.log('PASS: two native selector9 source preparations and two full mirrors; '+
      'real tag A/9/9 and exit source0; missing A-to-B writer adapter remains explicit.');
  }
}
module.exports={check};
