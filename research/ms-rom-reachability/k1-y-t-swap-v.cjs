#!/usr/bin/env node
'use strict';
// Verified conditional secondary V reader after the Y/T preparation.
// No machine-state restoration or hidden reads in the keyboard operation.
const entry=require('./k1-y-t-entry.cjs');
const defaults={...entry.defaults,afterClone:[['↔']]};
const finish=(c,o={},record=()=>{})=>entry.finish(c,{...defaults,...o,afterClone:[['↔']]},record);
const run=(o={})=>entry.run({...defaults,...o,afterClone:[['↔']]});
module.exports={defaults,finish,run};
