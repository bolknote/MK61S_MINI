#!/usr/bin/env node
'use strict';
// Fixed one-ring timing diagnostic for the already ROM-selected Cx route.
// Only native tick()/press()/runFrames() calls. No state setters or adaptive
// timing selected from internal registers; observers inspect between actions.
const zw=require('./k1-zw-entry.cjs');
const frame=require('./k1-frame-boundary-probe.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...zw.defaults,deepTail:[['K','0'],['В↑']],deepTailPhases:[1,0],
  commandOffsets:Array.from({length:15},(_,i)=>i)};
function microCommands(c,n){for(let i=0;i<42*n;i++)c.tick();}
function finish(c,o={},record=()=>{}) {
  o={...defaults,...o};zw.finish(c,o,record);
  for(const [i,offset] of o.commandOffsets.entries()) {
    if(!Number.isInteger(offset)||offset<0||offset>=560)throw new Error('bad command offset');
    record('fine-clear/'+i);
    microCommands(c,offset);
    c.press('Сx');
    microCommands(c,560-offset);
    c.runFrames(8);
  }
  for(const [i,keys] of (o.afterClear??[]).entries()) {
    record('clear-tail/phase-'+i);c.runFrames(o.afterClearPhases?.[i]??0);
    stack.act(c,record,'clear-tail/'+i,keys);
  }
}
const run=(o={})=>frame.run({defaults,finish},o);
const traced=(o={})=>{
  o={...defaults,...o};return cap.run(o,finish,
    ['clone-prefix','clone-sign','after-clone-0','rotate/reserve','rotate/tail-0',
     'deep/prepare','deep/clone',...[0,1,2,3,4].map(i=>'deep/marker-'+i),
     ...o.deepTail.map((_,i)=>'deep/tail-'+i),
     ...o.commandOffsets.map((_,i)=>'fine-clear/'+i),
     ...(o.afterClear??[]).map((_,i)=>'clear-tail/'+i)]);
};
if(require.main===module) {
  const r=run(JSON.parse(process.env.K1_ZV_TIMING_OPTIONS||'{}'));
  console.log(JSON.stringify(r.rows.filter(e=>e.stage.startsWith('fine-clear/')||e.stage.startsWith('clear-tail/')||['immediate','done'].includes(e.stage))
    .map(({stage,phase,values,missing})=>({stage,phase,X:values.X,V:values.V,
      visible:['X','Y','Z','T'].map(n=>values[n]),lower:['U','V','W','Q'].map(n=>values[n]),
      marks:Object.entries(values).filter(([,v])=>v[4]==='F').map(([n])=>n),missing})),null,2));
}
module.exports={defaults,finish,run,traced,microCommands};
