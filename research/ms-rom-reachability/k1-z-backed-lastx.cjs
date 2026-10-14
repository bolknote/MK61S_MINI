#!/usr/bin/env node
'use strict';
// Connect the keyboard Y/T/V preparation to the previously conditional
// LastX(Q) path. Only the Z marker remains; this is not a clean exit.
const deep=require('./k1-z-backed-deep-entry.cjs');
const defaults={...deep.defaults,deepTail:[['K','0'],['F','В↑']],deepTailPhases:[1,1]};
const finish=(c,o={},record=()=>{})=>deep.finish(c,{...defaults,...o},record);
const run=(o={})=>deep.run({...defaults,...o});
const traced=(o={})=>deep.traced({...defaults,...o});
module.exports={defaults,finish,run,traced};
