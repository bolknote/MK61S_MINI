#!/usr/bin/env node
'use strict';
// Experimental upper continuation. The prefix's work registers are not
// restored; this is not an implementation of full K1.
const quiet=require('./probe_ms_clone_quiet_request.cjs');
const actions=(o={})=>[['F',','],['↔'],['↔'],['X→П','8'],['X→П','9'],...(o.upperTail??[])];
const options=(o={})=>({...o,afterQuiet:actions(o)});
const prepare=quiet.prepare;
const finish=(c,o={},record=()=>{})=>quiet.finish(c,options(o),record);
const run=(o={})=>quiet.run(options(o));
if(require.main===module)console.log(JSON.stringify(quiet.brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={actions,options,prepare,finish,run};
