#!/usr/bin/env node
'use strict';
// Read-only diagnostic snapshots at native frame boundaries. No synchronizing
// getters, state restoration, or clock steps are used between keyboard actions.
// The three tag maps are generated off-machine using the same physical wiring
// as probe_ee_ring_source.cjs. Full write traces remain the verification oracle.
const assert=require('node:assert/strict');
const cap=require('./k1-bank-v-capture.cjs');
const {aligned}=require('./probe_ee_ring_source.cjs');
const {fullMsPages}=require('./probe_c8_payload.cjs');
const {registers,program}=require('./probe_a8_ms_readout.cjs');
const {snapshotFromRing}=require('./k1-permutation-oracle.cjs');
const {raw}=require('./probe_ms_two_markers.cjs');
const names=['marker','control','P7','P8','P9','P10','W','Q','Z','T','U','V','Y','X','X1'];
const locations=[[1,41],[1,83],[1,125],[1,167],[1,209],[1,251],
  [2,41],[2,83],[2,125],[2,167],[2,209],[2,251],[3,41],[4,41],[5,41]];
const tags=[null,...[252,252,42,42,42].map(n=>new Array(n))];
for(let page=0;page<15;page++) {
  const [chip,end]=locations[page];
  for(let n=0;n<42;n++)tags[chip][end-41+n]=[names[page],n];
}
const maps=new Map();let j=84,k=0;
for(let frame=0;frame<3;frame++) {
  maps.set(j,tags.map(a=>a&&a.map(t=>t.slice())));
  for(let t=0;t<560*42;t++) {
    const next=[tags[2][j],tags[3][k],tags[4][k],tags[5][k],tags[1][j]];
    [tags[3][k],tags[4][k],tags[5][k],tags[1][j],tags[2][j]]=next;
    j=(j+1)%252;k=(k+1)%42;
  }
}
assert.equal(j,84);assert.equal(k,0);assert.deepEqual(tags,maps.get(84));
function peek(c) {
  assert.equal(c.ik1302.tickIndex,0);
  const map=maps.get(c.ir2a.tickIndex);assert.ok(map,'native frame phase');
  const chips=[null,c.ir2a,c.ir2b,c.ik1302,c.ik1303,c.ik1306];
  const ring=Object.fromEntries(names.map(n=>[n,new Array(42)]));
  for(let id=1;id<=5;id++)for(let i=0;i<chips[id].memory.length;i++) {
    const [slot,n]=map[id][i];ring[slot][n]=chips[id].memory[i];
  }
  return ring;
}
function run(probe,o={}) {
  o={...probe.defaults,...o};const calc=cap.prepare(o);
  const before=fullMsPages(calc),beforeRegisters=registers(calc),beforeProgram=program(calc);
  aligned(calc);
  const initial=peek(calc),original=snapshotFromRing(initial).words;
  const rows=[];
  const record=stage=>{
    const ring=peek(calc),stored=snapshotFromRing(ring);
    const values=Object.fromEntries(names.map(n=>[n,raw(ring[n])]));
    const live=[...stored.words,...['X1','X','Y','Z','T'].map(n=>values[n])];
    rows.push({stage,phase:calc.ir2a.tickIndex,values,
      missing:original.filter(x=>!live.includes(x)),registers:stored.words.slice(0,15),ring});
  };
  probe.finish(calc,o,record);record('immediate');calc.runFrames(3);record('done');
  return {options:o,calc,before,beforeRegisters,beforeProgram,initial,rows};
}
function brief(r) {
  return {options:r.options,rows:r.rows.map(({ring,...row})=>row)};
}
module.exports={peek,run,brief};
