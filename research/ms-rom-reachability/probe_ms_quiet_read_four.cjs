#!/usr/bin/env node
'use strict';
const fifth=require('./probe_ms_quiet_fifth_zero.cjs');
const quiet=require('./probe_ms_clone_quiet_request.cjs');
const upper=require('./probe_ms_quiet_upper.cjs');
const suffix=[['П→X','6'],['F',','],['F',','],['F',','],['X→П','/-/']];
const options=(o={})=>({...o,afterQuiet:[...upper.actions(fifth.options(o)),...suffix,...(o.afterFour??[])]});
const prepare=fifth.prepare;
const finish=(c,o={},record=()=>{})=>quiet.finish(c,options(o),record);
const run=(o={})=>quiet.run(options(o));
if(require.main===module)console.log(JSON.stringify(quiet.brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={suffix,options,prepare,finish,run};
