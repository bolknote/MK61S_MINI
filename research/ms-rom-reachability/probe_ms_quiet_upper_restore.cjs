#!/usr/bin/env node
'use strict';
// Conditional upper read/restore cycle. W and the lower work area remain;
// neither full K1 nor a normal calculator exit is claimed.
const four=require('./probe_ms_quiet_read_four.cjs');
const suffix=[['П→X','9'],['X→П','ВП'],['П→X','8'],['X→П','Сx'],
  ['П→X',','],['↔'],['Сx'],['П→X','1'],['П→X','/-/'],['П→X','ВП'],['П→X','Сx']];
const options=(o={})=>({...o,afterFour:[...suffix,...(o.afterRestore??[])]});
const prepare=four.prepare;
const finish=(c,o={},record=()=>{})=>four.finish(c,options(o),record);
const run=(o={})=>four.run(options(o));
if(require.main===module)console.log(JSON.stringify(require('./probe_ms_clone_quiet_request.cjs').brief(run(process.argv[2]?JSON.parse(process.argv[2]):{})),null,2));
module.exports={suffix,options,prepare,finish,run};
