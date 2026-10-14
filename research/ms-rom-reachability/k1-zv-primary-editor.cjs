#!/usr/bin/env node
'use strict';
// Fixed-time primary-editor diagnostic from the same keyboard-created
// real/Z/V state. No internal-state reads, setters or snapshot restoration.
const zw=require('./k1-zw-entry.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const {microCommands}=require('./k1-zv-clear-timing.cjs');
const defaults={...zw.defaults,fullUpper:['402','9022','9033','9044'],
  deepTail:[['K','0'],['В↑']],deepTailPhases:[1,0],
  edits:[{key:'/-/',offset:3,phase:0}],afterEdit:[],afterEditPhases:[]};
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};zw.finish(c,o,record);
  for(const [i,edit] of o.edits.entries()) {
    if(!Number.isInteger(edit.offset)||edit.offset<0||edit.offset>=560)throw new Error('bad command offset');
    record('edit/phase-'+i);c.runFrames(edit.phase??0);
    record('edit/'+i);microCommands(c,edit.offset);c.press(edit.key);
    microCommands(c,560-edit.offset);c.runFrames(edit.wait??8);
  }
  for(const [i,keys] of o.afterEdit.entries()) {
    record('edit-tail/phase-'+i);c.runFrames(o.afterEditPhases[i]??0);
    stack.act(c,record,'edit-tail/'+i,keys);
  }
}
const run=(o={})=>frame.run({defaults,finish},o);
const traced=(o={})=>{
  o={...defaults,...o};return cap.run(o,finish,
    ['clone-prefix','clone-sign','after-clone-0','rotate/reserve','rotate/tail-0',
     'deep/prepare','deep/clone',...[0,1,2,3,4].map(i=>'deep/marker-'+i),
     ...o.deepTail.map((_,i)=>'deep/tail-'+i),...o.edits.map((_,i)=>'edit/'+i),
     ...o.afterEdit.map((_,i)=>'edit-tail/'+i)]);
};
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_ZV_EDITOR_OPTIONS||'{}'));
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('edit')||['immediate','done'].includes(e.stage))
    .map(({stage,phase,values,missing})=>({stage,phase,values,missing})),null,2));
}
module.exports={defaults,finish,run,traced};
