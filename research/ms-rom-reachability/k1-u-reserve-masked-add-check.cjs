#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-u-reserve-masked-add.cjs');
const reserve=require('./k1-single-v-u-reserve-check.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const repack=require('./k1-visible-marker-repack-check.cjs');
const {prefixView}=require('./k1-y-t-swap-v-check.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const control=require('./k1-x1-retry-reader-check.cjs');
const same=(a,b,label)=>label===undefined?assert.deepEqual(a,b):assert.deepEqual(a,b,label);
const word=(ring,n,value)=>[...value].reverse().forEach((x,j)=>{ring[n][1+3*j]=parseInt(x,16);});
const visible=e=>['X1','X','Y','Z','T'].map(n=>raw(e.ring[n]));
const marks=e=>Object.keys(e.ring).filter(n=>e.ring[n][22]===15).sort();
const m='9990FFFFFFF0',inv='00008FFFFFFF';

function surface(o={}) {
  const ds=['1,','2,','3,','4,'],a=control.record(ds,o,probe.finish);
  same(a,control.record(ds,{...o,incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']},probe.finish));
  same(a.seen,ds);const keys=a.actions.filter(x=>x[0]==='key').length;
  return {keys,frames:2*keys+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0),
    publicDisplayOnly:true,fixturePreparationExcluded:true,assumedSuccessfulAttempts:1};
}

function check(r,negative=false,endStage='done') {
  if(endStage!=='done')r=prefixView(r,endStage);
  const prefix=reserve.check(r,'u-reserve/tail-0');
  checks.protectedFields(r,[0],['U','V','W','Q','P7']);
  same(r.traced.writes.filter(w=>w.slot==='marker'&&w.nibble%3===1&&w.nibble<37&&w.before!==w.value),[],
    'true numeric marker unchanged including transient writes');
  const [u,v,w,q,a,b]=['U','V','W','Q','P7','P8'].map(n=>r.before[n].slice(2)),p=r.beforeRegisters[0];
  const begin=checks.boundary(r,'u-reserve/tail-0'),cleared=checks.boundary(r,'u-reserve/phase-1');
  const masked=checks.boundary(r,'u-reserve/tail-2'),end=checks.boundary(r,'done');
  same(visible(cleared),[inv,v,u,q,m]);same(marks(cleared),['T','marker']);
  same(['U','V','W','Q'].map(n=>raw(cleared.ring[n])),[v,v,v,p]);
  same(visible(masked),[v,v,u,q,m]);same(marks(masked),['T','marker']);
  same(raw(masked.ring.U),'36'+v.slice(2));
  same([masked.ring.control[34],masked.ring.control[31]],[3,15]);
  const allowed=new Set(),paths=[];
  for(let i=0;i<3;i++) {
    const es=r.traced.events.filter(e=>e.stage==='u-reserve/tail-'+i);
    assert.ok(es.every(e=>e.otherChips?.[4]&&e.otherChips?.[5]),'all-chip observations');
    const gates=es.filter(e=>e.ip===0x9C);
    same(gates.map(e=>[e.slot,e.nextIp]),i===0?[['U',0x9E],['U',0x9E]]:
      i===1?[['control',0x9E],['control',0x9E]]:[['U',0x9D],['control',0x9E],['control',0x9E]]);
    const reads=es.filter(e=>e.ip===0xEE);
    same(reads.map(e=>[e.slot,e.raw,e.nextIp]),[[i?'W':'X',v,0xA1],['X',v,0xE3]]);
    const copies=es.filter(e=>e.ip===0xE9);same(copies.length,1);
    repack.exactCopy(r,copies[0],i?'X1':'V',v);allowed.add('3:'+copies[0].command);
    const requests=es.filter(e=>e.ip===0xA3);same(requests.length,1);
    const req=requests[0],where=i?'U':'control',opcode=i===2?0x10:0x36;
    same(req.slot,where);const expected=ringAt(r,req.command);
    const values=[parseInt(v[2],16),opcode%16,opcode>>4];
    [28,31,34].forEach((n,j)=>{expected[where][n]=values[j];});
    same(ringAt(r,req.command+1),expected,'only the three request-header tetras change');
    same(r.traced.writes.filter(w=>w.command===req.command).map(w=>[w.chip,w.slot,w.nibble,w.value]),
      [28,31,34].map((n,j)=>[3,where,n,values[j]]));allowed.add('3:'+req.command);
    const late=es.filter(e=>e.ip===0xE7);same(late.length,1);
    repack.exactCopy(r,late[0],'W',v);allowed.add('3:'+late[0].command);
    paths.push({gates:gates.map(e=>[e.command,e.slot,e.nextIp]),
      read:reads[0].command,copy:copies[0].command,request:req.command,late:late[0].command});
  }
  const ack3=r.traced.writes.filter(w=>w.command>=begin.command&&w.command<cleared.command&&w.chip===5&&w.before!==w.value);
  same(ack3.map(w=>[w.ip,w.slot,w.nibble,w.before,w.value]),[[0xFD,'control',31,6,15]]);
  allowed.add('5:'+ack3[0].command);
  const last=r.traced.events.filter(e=>e.stage==='u-reserve/tail-2');
  const ww=r.traced.writes.filter(w=>w.command>=masked.command&&w.command<end.command&&w.chip===4);
  const ack=ww.filter(w=>w.ip===0x27);
  same(ack.map(w=>[w.slot,w.nibble,w.before,w.value]),[['U',31,0,15],['U',31,15,15]]);
  for(const wr of ack)allowed.add('4:'+wr.command);
  const writes=ww.filter(w=>w.ip!==0x27);assert.ok(writes.length);
  const first=writes[0].command;
  same(writes.map(w=>[w.command-first,w.ip,w.slot,w.nibble]),['W','Q','P7','P8'].flatMap((n,i)=>
    Array.from({length:12},(_,j)=>[i,i===3?0x2A:0x3A,n,1+3*j])),'exact four-word binary output including unchanged P8');
  for(let i=0;i<4;i++)allowed.add('4:'+(first+i));
  const result=raw(end.ring.W),computed=raw(ringAt(r,first+4).W);
  if(negative) {
    same(computed,'002020099012','201 + (-9.8765432E-3) at the arithmetic output');
    assert.notEqual(computed,p,'addition does not absorb this v exactly');
    same(result,v,'later primary formatting replaces the computed sum');
  } else {same(result,p);same(computed,p);}
  const output=ringAt(r,first);word(output,'W',computed);word(output,'Q',a);word(output,'P7',b);
  same(ringAt(r,first+4),output,'whole 630-tetra binary output endpoint');
  const source=last.find(e=>e.command>paths[2].request&&e.otherChips[4].ip===0x52&&e.otherChips[4].slot==='W');
  assert.ok(source);const second=last.find(e=>e.command===source.command+1);
  same([raw(source.otherChips[4].m),second.otherChips[4].ip,second.otherChips[4].slot,raw(second.otherChips[4].m)],
    [v,0x53,'Q',p],'the actual arithmetic operands are W=v and Q=p');
  if(negative)assert.ok(first+3<paths[2].late,'shorter arithmetic completes before the destructive late write');
  else assert.ok(paths[2].late<ack[0].command&&ack[0].command<first,'late primary write precedes arithmetic output');
  const expected=structuredClone(begin.ring);
  for(const [n,value] of Object.entries({X1:v,U:'1F'+v.slice(2),V:v,W:result,Q:a,P7:b,
    control:'3F'+v[2]+raw(begin.ring.control).slice(3)}))word(expected,n,value);
  same(end.ring,expected,'full masked-add endpoint');same(marks(end),['T','marker']);
  same(r.afterRegisters,r.beforeRegisters.map((x,i)=>i?x:w));
  same(r.traced.writes.filter(w=>w.command>=begin.command&&w.command<end.command&&w.before!==w.value
    &&!allowed.has(w.chip+':'+w.command)),[],'all changed tetras have declared chip/command owners');
  const rows=repack.boundaryLosses(r);
  same(rows.filter(x=>x.missing.length).map(x=>[x.stage,x.missing]),negative?[['done',[p]]]:[]);
  return {prefix,boundaries:rows.length,paths,realControlAck:ack3[0].command,
    arithmeticSources:source.command,requestAck:ack[0].command,arithmeticOutput:first,
    all23LiveAtEveryBoundary:!negative,exactAbsorption:!negative,computed,result,
    upperAInQ:true,upperBInP7AndP8:true,hiddenVRemoved:true,remainingMarker:'T',
    uOnlyInY:true,qOnlyInZ:true,normalExit:false,fullK1:false,
    ...(negative?{rejected:'p + v differs from p and finishes before the late overwrite',
      originalPHasNoExactWordCopy:true,notGeneralImpossibility:true}:{})};
}

if(require.main===module) {
  const negative=!!process.env.K1_MASKED_ADD_NEGATIVE;
  const o={...probe.defaults,...JSON.parse(process.env.K1_MASKED_ADD_OPTIONS||'{}')};
  if(negative)o.values=['-1.2345678E-42','-7.654321E-23','-9.8765432E-3','-12345678'];
  console.log('PASS keyboard surface:',JSON.stringify(surface(o)));
  const r=probe.run(o);console.log('PASS '+(negative?'numeric rejection':'masked add')+':',JSON.stringify(check(r,negative)));
  if(process.env.K1_MASKED_ADD_UNOBSERVED)console.log('PASS all fields without observer:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={surface,check};
