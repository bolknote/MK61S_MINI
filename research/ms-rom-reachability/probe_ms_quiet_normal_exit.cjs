#!/usr/bin/env node
'use strict';
// Conditional upper read/restore with no remaining M2 markers outside marker.
// Lower Ms and ordinary work registers are consumed. This is NOT full K1.
const p=require('./probe_ms_upper_w_cleanup.cjs');
const tail=[['П→X','/-/'],['Сx'],['П→X','0'],['П→X','5'],
  ['П→X','0'],['Сx','В↑','В↑','В↑','+']];
const options=(o={})=>({...o,stageB:true,zeroBeforeMarker:o.zeroBeforeMarker??true,traceFrom:o.traceFrom??32,
  cleanupTail:[...tail,...(o.verifyExit?[['2','В↑','3','+'],['Сx'],['В/О','С/П']]:[]),...(o.afterExit??[])]});
const prepare=p.prepare;
const finish=(c,o={},record=()=>{})=>p.finish(c,options(o),record);
const run=(o={})=>p.run(options(o));
module.exports={tail,options,prepare,finish,run};
