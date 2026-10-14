#!/usr/bin/env node
'use strict';
// Verified conditional closure: drop T by RCL0, recover q from LastX,
// then blind-push only while old W is a duplicate. See the accompanying
// checker for two fixtures, preservation and working exit, not full K1.
const reserve=require('./k1-y-t-swap-v.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const stack=require('./k1-visible-stack-cycle.cjs');
const defaults={...reserve.defaults};
function finish(c,o={},record=()=>{}) {
  reserve.finish(c,o,record);
  // ENTER can be accepted after T and push into W/Q/P7/P8. RCL0 instead
  // converges on D6(U) -> A7(V), whose scan starts after the T marker.
  stack.act(c,record,'reserve/drop-t',o.dropByEnter?['В↑']:['П→X','0']);
  if(o.stopAfterDrop)return;
  stack.act(c,record,'reserve/read-q',['F','В↑']);
  stack.blindPush(c,o,s=>record('reserve/restore/'+s));
  if(o.verifyExit) {
    stack.act(c,record,'post/manual',['Сx','2','В↑','3','+']);
    stack.act(c,record,'post/zero',['Сx']);
    stack.act(c,record,'post/program',['В/О','С/П'],12);
  }
}
const run=(o={})=>cap.run({...defaults,...o},finish,
  ['clone-prefix','clone-sign','after-clone-0','reserve/drop-t','reserve/read-q',
    ...['push','push-clear','push-return'].map(s=>'reserve/restore/'+s)]);
module.exports={defaults,finish,run};
