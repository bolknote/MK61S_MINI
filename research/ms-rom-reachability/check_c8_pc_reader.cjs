#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const {read}=require('./probe_c8_pc_reader.cjs');

function differences(a,b,path='') {
  if(a&&b&&typeof a==='object'&&typeof b==='object')
    return [...new Set([...Object.keys(a),...Object.keys(b)])].flatMap(k=>
      differences(a[k],b[k],path?path+'.'+k:k));
  return a===b?[]:[{path,before:a,after:b}];
}

function check(value,units,negative,options={},expectedSlots=['W']) {
  const result=read(value,options),r=result.report;
  const expectedRaw=negative?`${String(units+1).padStart(3,'0')}010000000`:
    `0000${units}0000000`;
  const expectedPc=String(units)+(negative?'9':'0');
  assert.equal(r.pc,expectedPc);
  assert.equal(r.p8,expectedRaw,'actual numeric P8, not just a display artifact');
  assert.equal(result.calc.readRegister('8',{syncPhase:false}),r.x,'X agrees with P8');
  assert.deepEqual(r.reads.map(e=>e.slot),expectedSlots);
  assert.deepEqual(r.wholePrimitives,expectedSlots.map(()=>'c8'));
  const events=result.result.events;
  const c8=events.filter(e=>e.ip===0xC8).at(-1);
  const loaded=events.find(e=>e.command===c8.command+1);
  for(let i=1;i<42;i+=3) assert.equal(loaded.r[i],c8.m[i],`C8 loads nibble ${i}`);
  const shift=events.find(e=>e.command>c8.command && e.ip===0x08);
  assert.ok(shift);
  assert.equal(shift.r[25],c8.m[25],'sign came from the last actual C8');
  assert.equal(shift.r[28],c8.m[28],'exponent units came from the last actual C8');
  const d7=events.find(e=>e.command===shift.command+2);
  assert.equal(d7.ip,0xD7);
  assert.equal(d7.r[31],c8.m[25]);
  assert.equal(d7.r[34],c8.m[28]);
  console.log(`PASS ${JSON.stringify(value)}: C8 ${expectedSlots.join(' -> ')}; `+
    `PC ${r.pc}; X=P8=${r.x}; ${JSON.stringify(options)}`);
  return result;
}

function main() {
  let positive,negative,unitOne;
  for(let units=0;units<=9;units++) for(const sign of [false,true]) {
    const result=check(`${sign?'-':''}1.0234567E${30+units}`,units,sign);
    if(units===0) {if(sign) negative=result;else positive=result;}
    if(units===1&&!sign) unitOne=result;
  }
  assert.deepEqual(differences(positive.atFirstC8,negative.atFirstC8),[
    {path:'ik1302.m.25',before:0,after:9},
  ],'before C8 all five chips differ ONLY in the unread sign nibble');
  assert.deepEqual(differences(positive.atFirstC8,unitOne.atFirstC8),[
    {path:'ik1302.m.28',before:0,after:1},
  ],'before C8 all five chips differ ONLY in the unread exponent-units nibble');
  console.log('PASS causal controls: the whole machine differs in only M25 or M28 at C8.');
  check('8.7654321E31',1,false);
  check(['1E10','-8.7654321E32','333'],2,true,{},['W','V']);
  check(['1E10','1E10','-1.2345678E34'],4,true,{},['W','V','U']);
  for(const options of [{phaseOffset:1},{phaseOffset:2},
                        {settleFrames:10,readoutIdle:12}])
    check('-1.0234567E39',9,true,options);
  console.log('PASS: 26 keyboard-only partial Ms reads. Sign and exponent units '+
    'reach ordinary X/P8. The separate eight-digit display reader is tested in '+
    'check_c8_mantissa_reader.cjs; automatic mantissa transfer to X/P8 is still separate work.');
}

if(require.main===module) main();
module.exports={check,differences};
