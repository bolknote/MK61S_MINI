#!/usr/bin/env node
'use strict';
// Three words are prepared by ONE native program, before any late false
// marker is exposed to E5. This avoids interactive programming in an
// abnormal scanner and avoids computing the marker after ST35 is saved.
const assert=require('node:assert/strict');
const {MK61,trace,aligned}=require('./probe_ee_ring_source.cjs');
const {rawMemoryRegister}=require('./check_ac_signature_keyboard.cjs');
const {preparePayload,fullMsPages}=require('./probe_c8_payload.cjs');
const PROGRAM=[0x0D,0x3A,0x35,0x48,
  0x0D,1,0x0C,7,5,0x22,0x22,0x22,0x60,0x12,0x44,
  0x0D,1,0x0C,8,7,0x22,0x22,0x22,0x61,0x12,0x47,0x50];
const PROGRAM_KEYS=['Сx','K','Сx','K','8','X→П','8',
  'Сx','1','ВП','7','5','F','*','F','*','F','*','П→X','0','*','X→П','4',
  'Сx','1','ВП','8','7','F','*','F','*','F','*','П→X','1','*','X→П','7','С/П'];

function prepare({values=null,seedLowDigit=5,captureProgram=false,markerKind='logical',calc=new MK61()}={}) {
  assert.ok(Number.isInteger(seedLowDigit)&&seedLowDigit>=0&&seedLowDigit<=9);
  assert.ok(['logical','classic'].includes(markerKind));
  for(const name of ['loadProgram','writeCommand','setRegister','writeNumber'])
    calc[name]=()=>{throw new Error('Forbidden state setter: '+name);};
  if(values!==null) preparePayload(values,calc);
  const prefix=markerKind==='logical'?PROGRAM.slice(0,4):Array(4).fill(0x54);
  const prefixKeys=markerKind==='logical'?PROGRAM_KEYS.slice(0,7):Array(4).fill(['K','0']).flat();
  const program=[...prefix,...PROGRAM.slice(4),...(captureProgram?[0x49,0x50]:[])];
  const programKeys=[...prefixKeys,...PROGRAM_KEYS.slice(7),...(captureProgram?['X→П','9','С/П']:[])];
  calc.pressSequence(['В/О','F','ВП',...programKeys,'F','/-/','В/О']);
  assert.deepEqual(program.map((_,i)=>calc.readCommand(i)),program);
  if(markerKind==='classic') {
    // Error/EXP/NOP yields just one F, unlike the seven-F fractional word.
    // Unlike the logical form, this word survives a manual register store.
    for(const key of ['Сx','K','-','ВП','K','0','X→П','8']) calc.press(key).runFrames(12);
    aligned(calc);assert.equal(rawMemoryRegister(calc,8),'0000F0000000');
  }
  calc.inputNumber('1.0000001',{clear:true}).pressSequence(['X→П','0']);
  calc.inputNumber('1.000000'+seedLowDigit+'E4',{clear:true}).pressSequence(['X→П','1']);
  calc.pressSequence(['В/О','С/П']).runFrames(20);
  aligned(calc);
  for(const [reg,raw] of [[4,'600010000001'],[7,'70001000000'+seedLowDigit],
    [8,markerKind==='logical'?'9990FFFFFFF0':'0000F0000000']])
    assert.equal(rawMemoryRegister(calc,reg),raw,'the native preparatory program must finish');
  return calc;
}

function finish(calc,{placement='late',settleFrames=8,phaseOffset=0,markerLifts=0,
  markerLift='enter',finalRecall=true,clearKey='Сx'}={},record=()=>{}) {
  assert.ok(['none','inline','late','before-clear','before-address'].includes(placement));
  assert.ok(Number.isInteger(settleFrames)&&settleFrames>=1);
  assert.ok(Number.isInteger(phaseOffset)&&phaseOffset>=0&&phaseOffset<=2);
  assert.ok(Number.isInteger(markerLifts)&&markerLifts>=0&&markerLifts<=3);
  const liftKeys={enter:['В↑'],'last-x':['F','В↑'],'recall-zero':['П→X','3']}[markerLift];
  assert.ok(liftKeys,'known stack-lift operation required');
  assert.ok(['Сx','5','8'].includes(clearKey));
  calc.runFrames(phaseOffset);
  const marker=['marker',['П→X','8']];
  const actions=[['auto',['F','/-/']],['clear',[clearKey]],['seed',['П→X','7']],
    ['save',['F','/-/']],
    ...(placement==='before-clear'?[marker]:[]),['clear-again',[clearKey]],
    ...(placement==='before-address'?[marker]:[]),['address',['БП','В↑','0']],
    ...(placement==='late'?[marker]:[]),
    ...(placement==='inline'?[['marker',['Сx','K','Сx','K','8']]]:[]),
    ...Array.from({length:markerLifts},(_,i)=>['lift-marker-'+(i+1),liftKeys]),
    ...(finalRecall?[['recall',['П→X','4']]]:[])];
  const stages=[];
  for(const [label,keys] of actions) {
    record(label);calc.pressSequence(keys).runFrames(settleFrames);
    const k=calc.ik1302;
    stages.push({label,pc:k.r[31]+16*k.r[34],ip:k.r[36]+16*k.r[39],r2:k.r[2],r5:k.r[5],r23:k.r[23],
      st35:k.stack[35],display:calc.displayText()});
  }
  return stages;
}

function run(options={}) {
  const calc=prepare(options),before=fullMsPages(calc);
  let stage='',stages;
  const traced=trace(calc,c=>{stages=finish(c,options,label=>{stage=label;});},
    {extraIps:Array.from({length:256},(_,i)=>i),fullState:true,allWrites:true,
      ringAt:e=>{e.stage=stage;return [0xAC,0xEE,0xE7,0xA8,0xA9,0x93].includes(e.ip);}});
  const es=traced.events;
  const singles=es.filter((e,i)=>e.ip===0xA8&&e.s1===14&&es[i-1]?.ip===0xEE);
  const blocks=[];
  for(let i=0;i<es.length-4;i++) if(es[i].ip===0xE7&&es[i].s1===8&&
    es.slice(i+1,i+4).every(e=>e.ip===0xA8)&&es[i+4].ip===0xA9) {
    blocks.push({body:es.slice(i,i+4),after:es[i+4],exit:es[i+5],
      writes:traced.writes.filter(w=>w.command>=es[i].command&&w.command<es[i+4].command)});
  }
  aligned(calc);
  return {calc,stages,traced,singles,blocks,before,after:fullMsPages(calc)};
}

if(require.main===module) {
  const r=run({placement:process.argv[2]||'late'});
  console.log(JSON.stringify({stages:r.stages,singles:r.singles.map(e=>({slot:e.slot,command:e.command})),
    blocks:r.blocks.filter(b=>b.body[0].stage==='recall').map(b=>({
      command:b.body[0].command,slots:b.body.map(e=>e.slot)})),before:r.before,after:r.after},null,2));
}
module.exports={PROGRAM,PROGRAM_KEYS,prepare,finish,run};
