#!/usr/bin/env node
'use strict';
// Fixed structure-directed ALL5 frontier, not a complete marker exit.
const {verify}=require('./three-bank-escape-ledger-all5.cjs');
const protocol=[{kind:'cx',operand:0,lead:0},{kind:'rcl',operand:9,lead:0},{kind:'swap',operand:0,lead:0},
  ...Array.from({length:5},()=>({kind:'rcl',operand:8,lead:0})),{kind:'cx',operand:0,lead:0},
  ...Array.from({length:3},()=>({kind:'rcl',operand:9,lead:0})),{kind:'cx',operand:0,lead:0},
  ...[8,5,8,5,8].map(operand=>({kind:'rcl',operand,lead:0}))];
function run(file,{holdNegative=false}={}) {
  const selected=holdNegative?[...protocol.slice(0,3),...Array.from({length:2},()=>({kind:'rcl',operand:9,lead:0})),...protocol.slice(3)]:protocol;
  const r=verify(file,selected);
  return{...r,divergence:r.divergence&&{action:r.divergence.action,words:r.divergence.words,field:r.divergence.field},
    boundary:r.boundary+' PRIMARY planning after SWAP disagrees and is not authoritative; all reported frontier values are literal ALL5.'};
}
if(require.main===module)console.log(JSON.stringify(run(process.argv[2],{holdNegative:process.argv.includes('--hold-negative')})));
module.exports={run,protocol};
