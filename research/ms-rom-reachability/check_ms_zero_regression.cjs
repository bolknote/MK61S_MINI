#!/usr/bin/env node
'use strict';
// Default options in the shared keyboard helpers must preserve earlier states.
const assert=require('node:assert/strict');
const {digest}=require('./check_c8_keyboard.cjs');
const values=['-1E-99','-1.2345678E-42','-9.8765432E99','12345678'];
function oldPair() {
  const r=require('./probe_ms_upper_write2.cjs').run({stress:true,phaseOffset:0,values,
    fullUpper:['3.2109876E-19','-4.3210987E31','1.2345678E-42','-9.8765432E17']});
  assert.equal(digest(r.calc),'46fe3ec90a1762543578521f21c26e6ace3a5dda0dba5305e68d8a039f803034');
  require('./check_ms_upper_write.cjs').checkPair(r);
  console.log('PASS unchanged previous upper-pair writer digest and integration checks.');
}
function oldReader() {
  const r=require('./probe_ms_read6_exit.cjs').run({stress:true,restoreLower:true,phaseOffset:0,values,
    upperValues:['6.5432109E-23','-8.7654321E-17','333','444']});
  assert.equal(digest(r.calc),'de2a43269a8271422b6723fd44bd539ab4d99e3b02117cef09e1fc75eb06111a');
  require('./check_ms_read6_exit.cjs').check(r);
  console.log('PASS unchanged previous six-word reader digest and integration checks.');
}
oldPair();oldReader();
