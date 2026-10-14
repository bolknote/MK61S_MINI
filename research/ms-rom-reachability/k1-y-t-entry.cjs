#!/usr/bin/env node
'use strict';
// Alternative final clone operation: produce visible Y/T markers while
// retaining all 23 originals in stored words on the checked fixtures.
// See k1-y-t-entry-check.cjs; no completed exit or full-domain claim.
const deep=require('./k1-repack-deep-clone-probe.cjs');
const defaults={...deep.defaults,fullUpper:['-1E-99','9022','9033','9044'],
  clonePrefix:[],cloneKeys:['↔'],clonePhase:0};
const finish=(c,o={},record=()=>{})=>deep.finish(c,{...defaults,...o,
  clonePrefix:[],cloneKeys:['↔'],clonePhase:0},record);
const run=(o={})=>deep.run({...defaults,...o,clonePrefix:[],cloneKeys:['↔'],clonePhase:0});
module.exports={defaults,finish,run};
