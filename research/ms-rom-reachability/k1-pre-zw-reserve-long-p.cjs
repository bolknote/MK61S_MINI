#!/usr/bin/env node
'use strict';
// Read P8 before the origin-moving suffix, so a long p may replace its
// old stored copy without losing the original P8 payload. Not a safe exit.
const zw=require('./k1-zw-entry.cjs');
const defaults={...zw.defaults,incoming:'1.2345678E42',
  afterW:[['K','0'],['П→X','0'],['F','В↑']],afterWPhases:[0,0,0]};
const finish=(c,o={},record=()=>{})=>zw.finish(c,{...defaults,...o},record);
const run=(o={})=>zw.run({...defaults,...o});
const traced=(o={})=>zw.traced({...defaults,...o});
module.exports={defaults,finish,run,traced};
