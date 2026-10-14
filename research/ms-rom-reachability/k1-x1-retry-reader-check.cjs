#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const probe=require('./k1-x1-retry-reader.cjs');
const checks=require('./k1-puhov-ring-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const {MK61}=require('./probe_ee_ring_source.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {ringAt}=require('./check_ms_clone_delayed_request.cjs');
const same=(a,b)=>assert.deepEqual(a,b),z='000000000000',m='0000F0000000';
function record(displays,o={},operation=probe.finish) {
  const actions=[],seen=[];let stage='';
  const methods={press(k){actions.push(['key',k,stage]);return this;},pressSequence:MK61.prototype.pressSequence,
    runFrames(n){assert.ok(Number.isInteger(n)&&n>=0);actions.push(['wait',n,stage]);return this;},
    displayText(){assert.match(stage,/(?:^|\/)attempt-\d\/display$/);const d=displays[seen.length];seen.push(d);return d;}};
  const c=new Proxy(methods,{get(t,k){assert.ok(Object.hasOwn(t,k),'forbidden live read '+String(k));return t[k];},
    set(){assert.fail('forbidden live assignment');}});
  const result=operation(c,o,s=>{stage=s;});return {actions,seen,result};
}
function surface() {
  const outputs=[];
  for(const displays of [['123,'],['0,','-1,2345678-42'],['0,','0,','0,']]) {
    const a=record(displays),b=record(displays,{incoming:'unread',p3:'unread',values:['unread'],fullUpper:['unread']});
    same(a,b);same(a.seen,displays);
    const keys=a.actions.filter(x=>x[0]==='key').length;
    const frames=keys*2+a.actions.filter(x=>x[0]==='wait').reduce((n,x)=>n+x[1],0);
    same([keys,frames],[42*displays.length,310*displays.length]);
    outputs.push({attempts:displays.length,keys,frames,publicDisplayOnly:true});
  }
  for(const d of ['',',','ЕГГОГ','garbage'])assert.throws(()=>record([d]),/Unexpected visible display/);
  return outputs;
}
function check(r) {
  checks.protectedFields(r,[0]);same(r.after,r.before);same(r.afterRegisters,r.beforeRegisters);
  const initial=snapshotFromRing(r.traced.events.find(e=>e.ring).ring),p=r.beforeRegisters[0],w=r.before.W.slice(2);
  assert.equal(new Set(initial.words).size,23,'distinct origins, including a possible zero W');
  const attempts=[];
  for(let i=0;i<3;i++) {
    const prefix='attempt-'+i+'/',stage=prefix+'retry-store';
    if(!r.traced.events.some(e=>e.stage===stage))break;
    const pre=checks.boundary(r,stage);
    same(['X1','X','Y','Z','T'].map(n=>raw(pre.ring[n])),[p,z,z,z,m]);
    same(raw(pre.ring.U,0),m);
    const read=r.traced.events.find(e=>e.stage===stage&&e.ip===0xEE);
    assert.ok(['W','X'].includes(read.slot),'only W or harmless X=0 is permitted');
    const value=read.slot==='W'?w:z;same(read.raw,value);
    const clean=checks.boundary(r,prefix+'retry-clean');same(raw(clean.ring.U,0),value);
    const store=r.traced.events.find(e=>e.stage===stage&&e.ip===0xD4);assert.ok(store);
    same(store.slot,'U');const expected=ringAt(r,store.command);
    [...value].reverse().forEach((v,j)=>{expected.U[3*j]=parseInt(v,16);});
    same(ringAt(r,store.command+1),expected);
    const recall=r.traced.events.find(e=>e.stage===prefix+'retry-clean'&&e.ip===0xD6);assert.ok(recall);
    same([recall.slot,recall.sp[0],recall.sp[1]],['U',0xA7,0xAC]);
    same(raw(ringAt(r,recall.command).U,0),value);
    const push=checks.exactPush(r,prefix+'retry-clean',['X','Y','Z','T']);same(push.displaced,m);
    const back=checks.boundary(r,prefix+'retry-recall-original');
    same(['X1','X','Y','Z','T'].map(n=>raw(back.ring[n])),[p,value,z,z,z]);
    const next=r.traced.events.find(e=>e.stage==='attempt-'+(i+1)+'/buffer-phase'&&e.ring)
      ??checks.boundary(r,'done');
    same(snapshotFromRing(next.ring).words,initial.words,'all 23 restored after each attempt');
    same(['X1','X','Y','Z','T'].map(n=>raw(next.ring[n])),[p,value,p,z,z]);
    same(Object.keys(next.ring).filter(n=>next.ring[n][22]===15),['marker']);
    const saved=checks.boundary(r,prefix+'buffer-recall-marker');
    assert.ok(r.traced.writes.filter(x=>x.command>=saved.command&&x.command<next.command&&x.slot==='X1'&&x.nibble%3===1)
      .every(x=>x.before===x.value),'buffer held through restore and visible selection');
    attempts.push({source:read.slot,value,readCommand:read.command,pushCommand:push.command});
  }
  assert.ok(attempts.length>=1&&attempts.length<=3);
  same(raw(checks.boundary(r,'done').ring.X),w);
  if(w!==z)assert.equal(attempts.at(-1).source,'W');
  else assert.equal(attempts.length,3,'real zero exercises the bounded fallback');
  return {phase:r.options.phaseOffset??0,attempts,readW:w,
    all23HeldAfterEveryAttempt:true,allMsHeldEvenTransiently:true,
    programAndServicesHeld:true,noFalseMarkers:true,fullK1:false,arbitraryTimingsProved:false};
}
if(require.main===module) {
  console.log('PASS visible-only controller:',JSON.stringify(surface()));
  if(process.env.K1_RETRY_SURFACE_ONLY)process.exit(0);
  const o={incoming:'-6.5432109E65',values:['811','12345678','-9.8765432E99','-1E-99'],
    ...JSON.parse(process.env.K1_RETRY_OPTIONS||'{}')};
  const r=probe.run(o);
  console.log('PASS safe retry W reader:',JSON.stringify(check(r)));
  if(process.env.K1_RETRY_UNOBSERVED)console.log('PASS observer-free full state:',
    keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={record,surface,check};
