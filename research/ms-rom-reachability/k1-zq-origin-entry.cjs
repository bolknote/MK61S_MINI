#!/usr/bin/env node
'use strict';
// Preserve the displaced top word in the physical real-marker numeric
// lane, then use LastX to move W's false marker to Q. Entry only: the
// physical marker must eventually be restored and v is still only in T.
const zw=require('./k1-zw-entry.cjs');
const defaults={...zw.defaults,afterW:[['П→X','0'],['F','В↑']],afterWPhases:[0,0]};
const finish=(c,o={},record=()=>{})=>zw.finish(c,{...defaults,...o},record);
const run=(o={})=>zw.run({...defaults,...o});
const traced=(o={})=>zw.traced({...defaults,...o});
module.exports={defaults,finish,run,traced};
