#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-zv-comma-closed.cjs');
const transfer=require('./k1-zv-comma-transfer-check.cjs');
const upper=require('./k1-zv-upper-closed-check.cjs');
const close=require('./k1-zv-nop-closed-check.cjs');
const previous=require('./k1-ytv-rcl-closed-check.cjs');
const zw=require('./k1-zw-entry-check.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const same=assert.deepEqual,neg='002910900000',recip='997991743119',zero='000000000000';
// Expected test operands, never read by the keyboard controller. Keeping
// the original defaults retains the exact 109 regression contract.
const defaultWorking={register:'002010900000',negative:neg,reciprocal:recip,
  numericRegister:109,numericReciprocal:-0.0091743119};
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const copy=(c,chip,n,v)=>[...v].reverse().map((x,j)=>[c,chip,n,1+3*j,parseInt(x,16)]);
const key=w=>[w.command,w.chip,w.slot,w.nibble,w.value];
const ordered=xs=>xs.toSorted((a,b)=>a[0]-b[0]||a[1]-b[1]||a[3]-b[3]);
function operation(r,i,endStage) {
  const stage='comma/tail-'+i,at=checks.boundary(r,stage),end=checks.boundary(r,endStage);
  const es=r.traced.events.filter(e=>e.stage===stage);
  assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]));
  const ww=r.traced.writes.filter(w=>w.command>=at.command&&w.command<end.command);
  return {stage,at,end,es,ww};
}
function sign(r,working=defaultWorking) {
  const neg=working.negative;
  const {at,end,es,ww}=operation(r,0,'comma/tail-1');
  same(r.beforeRegisters[8],working.register,'selected fixture R8');
  const gates=es.filter(e=>e.ip===0x9C),reads=es.filter(e=>e.ip===0xEE),late=es.filter(e=>e.ip===0xE7);
  same(gates.map(e=>[e.slot,e.nextIp]),[['control',0x9E]]);
  same([gates[0].r[30],gates[0].r[33],gates[0].s1,gates[0].r[41],gates[0].st[35],gates[0].st[25]],
    [11,0,11,15,15,0],'local CHS premises');
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['V',r.beforeRegisters[8],0xC1]]);same(late.length,1);
  same(es.filter(e=>[0xE9,0xA3,0xA8,0xD4,0xD6].includes(e.ip)),[]);
  repack.exactCopy(r,late[0],'X',neg);same(ww.map(key),copy(late[0].command,3,'X',neg));
  const expected=structuredClone(at.ring);deep.word(expected,'X',neg);same(end.ring,expected,'only X=-R8');
  return {readV:reads[0].command,writeNegativeToX:late[0].command,notACachedCopy:true,noStackLift:true};
}
function request(r,i,kind,working=defaultWorking) {
  const neg=working.negative,recip=working.reciprocal;
  const {stage,at,end,es,ww}=operation(r,i,'comma/tail-phase-'+(i+1));
  const isRecip=kind==='reciprocal',source=isRecip?neg:recip,result=isRecip?recip:r.before.U.slice(2);
  const code=isRecip?0x23:0x36,chip=isRecip?4:5,ackIp=isRecip?0x27:0xFD,outIp=isRecip?0x2A:0xFF;
  if(!isRecip)assert.ok(working.numericReciprocal<Number(r.options.values[3]),'fixture requires the machine reciprocal < u');
  same(raw(at.ring.X),source);
  same(es.filter(e=>e.ip===0x9C).map(e=>[e.slot,e.nextIp]),[['T',0x9E],['T',0x9E]]);
  const reads=es.filter(e=>e.ip===0xEE),saves=es.filter(e=>e.ip===0xE9),reqs=es.filter(e=>e.ip===0xA3),lates=es.filter(e=>e.ip===0xE7);
  same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[['X',source,0xA1],['X',source,0xE3]]);
  same([saves.length,reqs.length,lates.length],[1,1,1]);
  const save=saves[0],req=reqs[0],late=lates[0],target=isRecip?'X':'V';same(req.slot,'control');
  repack.exactCopy(r,save,'U',source);repack.exactCopy(r,late,target,source);
  if(!isRecip) {
    if(source[0]==='9')previous.formatter(r,stage,reads[1],late,0,['marker','Z']);
    else zw.formatter(r,stage,reads[1],late,'V',['marker','Z']);
  }
  const hv=[parseInt(source[2],16),code%16,code>>4],rh=ringAt(r,req.command);
  [28,31,34].forEach((n,j)=>{rh.control[n]=hv[j];});same(ringAt(r,req.command+1),rh);
  const other=ww.filter(w=>w.chip===chip),ack=other.filter(w=>w.ip===ackIp),out=other.filter(w=>w.ip!==ackIp);
  same(ack.map(w=>[w.slot,w.nibble,w.value]),[['control',31,15]]);same(out.length,12);
  const first=out[0].command;same(out.map(w=>[w.ip,...key(w)]),copy(first,chip,'X',result).map(v=>[outIp,...v]));
  const old=ringAt(r,first),changed=structuredClone(old);deep.word(changed,'X',result);
  same(ringAt(r,first+1),changed,'exact single-word result');
  if(isRecip) {
    same(first,late.command+1,'secondary result follows late primary overwrite by exactly one command');
    const consumer=es.find(e=>e.command===req.command).otherChips[4];
    same([consumer.ip,consumer.slot,consumer.r[29],consumer.st[36],consumer.st[39],consumer.st[37],consumer.st[40]],
      [0x6E,'marker',0,10,3,10,3],'local reciprocal premises');
    same(raw(es.find(e=>e.command===req.command+3).otherChips[4].m),neg,'secondary reads the selected negative operand');
  } else {same(raw(old.Y),result);assert.ok(reads[1].command<first&&first<late.command);}
  same(ordered(ww.map(key)),ordered([...copy(save.command,3,'U',source),
    ...[28,31,34].map((n,j)=>[req.command,3,'control',n,hv[j]]),
    [ack[0].command,chip,'control',31,15],...copy(late.command,3,target,source),...copy(first,chip,'X',result)]));
  const expected=structuredClone(at.ring);deep.word(expected,'U',source);deep.word(expected,'X',result);
  if(!isRecip)deep.word(expected,'V',source);
  [28,31,34].forEach((n,j)=>{expected.control[n]=hv[j];});expected.control[31]=15;
  same(end.ring,expected,'all 630 '+kind+' endpoint tetras');
  return {kind,request:req.command,latePrimary:late.command,secondaryResult:first,
    exactOutput:result,onlyDeclaredWrites:true};
}
function suffixView(r) {
  return {...r,traced:{...r.traced,events:r.traced.events.map(e=>{
    const m=/^comma\/tail(-phase)?-(\d+)$/.exec(e.stage);
    return m&&Number(m[2])>=2?{...e,stage:'w/tail'+(m[1]??'')+'-'+(Number(m[2])-2)}:e;
  })}};
}
function check(full,working=defaultWorking) {
  const r=full.options.verifyExit?prefixView(full,'post/manual'):full;
  same(r.options.afterTransfer,probe.defaults.afterTransfer);same(r.options.afterTransferPhases,probe.defaults.afterTransferPhases);
  const prefix=transfer.check(prefixView(r,'comma/tail-0',{afterTransfer:[],afterTransferPhases:[]}));
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);same(full.beforeProgram,full.afterProgram);
  same(full.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.before!==w.value),[]);
  const s=suffixView(r),operations=[sign(r,working),request(r,1,'reciprocal',working),request(r,2,'max',working),
    close.subtract(s),close.push(s,2),close.push(s,3),close.push(s,4)];
  const first=r.traced.events.find(e=>e.ring),end=checks.boundary(r,'done');
  const oracle=analyzeTrace({beforeEvent:first,afterEvent:end,writes:r.traced.writes,expectedMapping:upper.mapping});
  same(oracle.status,'PERMUTATION_INSTANCE_ONLY');same(oracle.fixedMapping.status,'matches_this_fixture');same(marks(end),['marker']);
  const rows=repack.boundaryLosses(full);same(rows.filter(e=>e.missing.length),[]);
  if(full.options.verifyExit) {
    same(full.beforeProgram.slice(0,5),[2,0x0E,3,0x10,0x50]);
    same(raw(checks.boundary(full,'post/zero').ring.X),'000050000000');
    same(raw(checks.boundary(full,'post/program').ring.X),zero);
    const done=checks.boundary(full,'done');same(raw(done.ring.X),'000050000000');same(marks(done),['marker']);
    same(snapshotFromRing(done.ring).words,snapshotFromRing(end.ring).words);
    same(full.traced.writes.filter(w=>w.command>=end.command&&w.before!==w.value&&
      ((w.nibble%3===0&&w.nibble<36)||(Object.hasOwn(full.before,w.slot)&&w.nibble%3===1)||[36,37,39,40].includes(w.nibble))),[]);
  }
  return {prefix,boundaries:rows.length,operations,cycles:oracle.data.cycles,all23Live:true,all23StoredAtExit:true,
    allExtraMarkersRemoved:true,other14OrdinaryUpper3ProgramAndServicesHeld:true,
    workingExitTested:!!full.options.verifyExit,shortUpperTransferClosed:true,
    fixtureR8:working.numericRegister,fixtureR1:r.options.fixtureRegisters?.[1]??102,
    comparison:working.numericReciprocal+' < u',arbitraryNumbersProved:false,repeatabilityProved:false,fullK1:false};
}
if(require.main===module) {
  const o={...probe.defaults,verifyExit:true,...JSON.parse(process.env.K1_COMMA_OPTIONS||'{}')};
  console.log('PASS surface:',JSON.stringify(deep.surface(o,probe.finish)));
  if(!process.env.K1_COMMA_SKIP_FRAME)console.log('PASS frames:',JSON.stringify(upper.frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS native:',JSON.stringify(check(r)));
  if(process.env.K1_COMMA_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={check,sign,request,suffixView,defaultWorking};
