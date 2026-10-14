#!/usr/bin/env node
'use strict';
// Revisit the historical short-number FIFO against ALL 23 stored words.
// This is a native keyboard probe, not a claim of a preserving permutation.
const capture=require('./k1-bank-v-capture.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const {snapshotFromRing,analyzeTrace}=require('./k1-permutation-oracle.cjs');
const defaults={incoming:'201',values:['811','822','833','844'],
  fullUpper:['9011','9022','9033','9044']};
function finish(c,o={},record=()=>{}) {
  c.runFrames(o.phaseOffset??0);
  const key=(label,k)=>{record(label);c.press(k).runFrames(o.keyFrames??12);};
  const group=(label,keys)=>keys.forEach((k,i)=>key(label+'/'+i,k));
  group('initial-clear',['Сx','В↑','В↑','В↑','+']);
  group('read-marker',['Сx','K','Сx','K','8']);
  group('read-oldest',Array(o.readLifts??6).fill('В↑'));
  if(o.rotate) {
    group('save-oldest',['X→П','9']);
    group('write-marker',['Сx','K','Сx','K','8']);
    group('write-oldest',['В↑','П→X','9',...Array(5).fill('В↑')]);
  }
  for(const [i,keys] of (o.tail??[]).entries())group('tail-'+i,keys);
}
const run=(o={})=>capture.run({...defaults,...o},finish);
function brief(r) {
  const es=r.traced.events;
  const firsts=es.filter((e,i)=>e.ring&&!es.slice(0,i).some(p=>p.stage===e.stage));
  const before=es.find(e=>e.ring),after=es.find(e=>e.stage==='done'&&e.ring);
  const oracle=analyzeTrace({beforeEvent:before,afterEvent:after,writes:r.traced.writes});
  return {options:r.options,oracle:{status:oracle.status,data:oracle.data,
    protection:oracle.protection,transientProtection:oracle.transientProtection},
    registers:r.afterRegisters.flatMap((v,i)=>v===r.beforeRegisters[i]?[]:[[i,r.beforeRegisters[i],v]]),
    ms:Object.entries(r.after).filter(([n,v])=>r.before[n]!==v).map(([n,v])=>[n,r.before[n],v]),
    stages:firsts.map(e=>({stage:e.stage,command:e.command,
      words:Object.fromEntries(['X1','X','Y','Z','T','U','V','W','Q'].map(n=>[n,raw(e.ring[n])]))})),
    msWrites:r.traced.writes.filter(w=>['U','V','W','Q','P7','P8','P9','P10'].includes(w.slot)&&
      w.nibble%3===1&&w.before!==w.value).map(w=>[w.command,w.chip,w.ip.toString(16),w.slot,w.nibble,w.before,w.value]),
    final:snapshotFromRing(after.ring)};
}
if(require.main===module) {
  const r=run(JSON.parse(process.argv[2]||'{}'));console.log(JSON.stringify(brief(r),null,2));
}
module.exports={defaults,finish,run,brief};
