#!/usr/bin/env node
'use strict';
// Intermediate upper-bank vacancy only. The displaced upper a remains in Y;
// original p is NOT backed up outside Q. No clean exit/full K1 is implied.
const upper=require('./k1-preserving-upper-rotation.cjs');
const cap=require('./k1-bank-v-capture.cjs');
const tail={afterUpperPhase:1,afterUpper:[['K','8'],['F','В↑']],afterUpperWaits:[8,8]};
const defaults={...upper.defaults,...tail};
function finish(c,o={},record=()=>{}) {upper.finish(c,{...o,...tail},record);}
const run=(o={})=>cap.run({...defaults,...o,...tail},finish,
  ['clone-prefix','clone-sign',...Array.from({length:4},(_,i)=>'after-clone-'+i),
    'after-upper-0','after-upper-1']);
module.exports={defaults,finish,run};
