#!/usr/bin/env node
'use strict';
const p=require('./probe_ms_quiet_upper.cjs');
const tail=(o={})=>[['Сx'],['F'],['В↑'],...(o.unsplitStore?[['X→П',',']]:[['X→П'],[',']])];
const options=(o={})=>({...o,upperTail:tail(o)});
const prepare=p.prepare;
const finish=(c,o={},record=()=>{})=>p.finish(c,options(o),record);
const run=(o={})=>p.run(options(o));
if(require.main===module)console.log(JSON.stringify(require('./probe_ms_clone_quiet_request.cjs').brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={tail,options,prepare,finish,run};
