#!/usr/bin/env node
'use strict';
// Fixed three-attempt U guard before the remaining W/Q reader. The native
// tests, not this wrapper, establish successful entry and preservation.
const p=require('./probe_ms_lower_secondary_exchange.cjs');
const options=o=>({...o,guardU:true});
const finish=(c,o={},record=()=>{})=>p.finish(c,options(o),record);
const runPrepared=(c,o={})=>p.runPrepared(c,options(o));
const run=(o={})=>p.run(options(o));
const runUnobserved=(o={})=>p.runUnobserved(options(o));
if(require.main===module)console.log(JSON.stringify(p.brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={prepare:p.prepare,finish,runPrepared,run,runUnobserved,brief:p.brief};
