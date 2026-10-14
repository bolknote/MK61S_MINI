#!/usr/bin/env node
'use strict';
// Research transfer, NOT a closed K1. The last upper word temporarily
// occupies the physical real-marker slot. Restoring that slot is mandatory
// before claiming normal exit. All live actions are keyboard/display only.
const reader=require('./k1-vw-upper-read.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...reader.defaults,originLeadPhase:0,saveLeadPhase:0};
function finish(c,o={},record=()=>{}) {
  reader.finish(c,{...o,afterRead:[],afterReadPhase:0},record);
  record('origin/phase');c.runFrames(o.originLeadPhase??0);
  stack.act(c,record,'origin/shift',['П→X','0']);
  if(o.stopAfterShift)return;
  record('origin/save-phase');c.runFrames(o.saveLeadPhase??0);
  stack.act(c,record,'origin/save',['X→П','7']);
  for(const [i,keys] of (o.afterOrigin??[]).entries()) {
    record('origin/tail-phase-'+i);c.runFrames(o.afterOriginPhases?.[i]??0);
    stack.act(c,record,'origin/tail-'+i,keys);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0','origin/shift','origin/save',
    ...(o.afterOrigin??[]).map((_,i)=>'origin/tail-'+i)]);
module.exports={defaults,finish,run};
