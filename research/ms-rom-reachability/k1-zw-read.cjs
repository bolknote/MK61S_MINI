#!/usr/bin/env node
'use strict';
// Read the second upper word after the retaining Z/W marker shift.
// This does not remove the markers or restore the only visible v.
const entry=require('./k1-zw-entry.cjs');
const defaults={...entry.defaults,afterW:[['K','0']],afterWPhases:[0]};
const finish=(c,o={},record=()=>{})=>entry.finish(c,{...defaults,...o},record);
const run=(o={})=>entry.run({...defaults,...o});
const traced=(o={})=>entry.traced({...defaults,...o});
module.exports={defaults,finish,run,traced};
