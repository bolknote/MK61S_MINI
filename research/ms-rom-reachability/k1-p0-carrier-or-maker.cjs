#!/usr/bin/env node
'use strict';
// Small keyboard-only maker study on a fresh calculator, no full trace.
// Diagnostic alignment/read occurs only after the entire key sequence.
const {MK61,aligned}=require('./probe_ee_ring_source.cjs');
function rawStack(c) {
  const locations={X1:[5,34],X:[4,34],Y:[3,34],Z:[2,118],T:[2,160]};
  return Object.fromEntries(Object.entries(locations).map(([n,[chip,address]])=>[n,
    Array.from({length:12},(_,j)=>c.memoryForChip(chip)[address-3*j].toString(16)).join('').toUpperCase()]));
}
const e01=[['Сx'],['0',',','0','1'],['K','-'],['ВП'],['K','0'],['ВП'],['2']];
function finish(c,{mask='10000000',withOr=true}={}) {
  for(const keys of e01)c.pressSequence(keys).runFrames(8);
  if(withOr) {
    c.pressSequence(['В↑','Сx']).runFrames(8);
    c.pressSequence([...mask]).runFrames(8);
    c.pressSequence(['K','/-/']).runFrames(8);
  }
  return c;
}
function run(o={}) {
  const c=new MK61();finish(c,o);aligned(c);
  return {options:o,display:c.displayText(),stack:rawStack(c)};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2]?JSON.parse(process.argv[2]):{}),null,2));
module.exports={e01,rawStack,finish,run};
