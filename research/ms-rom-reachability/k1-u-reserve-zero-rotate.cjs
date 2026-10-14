#!/usr/bin/env node
'use strict';
// Exact rotation replaces the earlier data-dependent addition. Clearing X
// guards its late formatter. Entry/cleanup still need native verification.
const reserve=require('./k1-single-v-u-reserve.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const defaults={...reserve.defaults};
function finish(c,o={},record=()=>{}) {
  reserve.finish(c,{...o,afterReserve:[['K','9'],['K','9'],['Сx'],['F',',']],
    afterReservePhases:[0,1,0,0],afterReserveWaits:[8,8,8,8]},record);
  if(o.clearMarker!==false)stack.act(c,record,'zero-rotate/drop-t',['П→X','0']);
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0',...[0,1,2,3].map(i=>'u-reserve/tail-'+i),
    'zero-rotate/drop-t']);
module.exports={defaults,finish,run};
