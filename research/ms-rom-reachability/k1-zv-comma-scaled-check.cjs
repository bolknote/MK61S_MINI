#!/usr/bin/env node
'use strict';
// Same keyboard protocol; initial R8/R1 are varied only in native fixtures.
// These are explicit instances, not a proof for all scaled mantissas.
const probe=require('./k1-zv-comma-closed.cjs');
const audit=require('./k1-zv-comma-closed-check.cjs');
const upper=require('./k1-zv-upper-closed-check.cjs');
const deep=require('./k1-z-backed-deep-entry-check.cjs');
const keyboard=require('./k1-puhov-keyboard-check.cjs');
const cases=[{
  name:'1090 / 202',options:{fixtureRegisters:{8:'1090',1:'202'}},
  working:{register:'003010900000',negative:'003910900000',reciprocal:'996991743119',
    numericRegister:1090,numericReciprocal:-0.00091743119},
},{
  name:'1.09E-17 / 302',options:{incoming:'301',
    values:['-8.7654321E-42','-6.543219E-23','-9.1234567E-17','-2.3456789E-30'],
    fullUpper:['703','-7.654321E23','1.2345678E42','8.7654321E-17'],
    fixtureRegisters:{8:'1.09E-17',1:'302'}},
  working:{register:'983010900000',negative:'983910900000',reciprocal:'016991743119',
    numericRegister:1.09e-17,numericReciprocal:-9.1743119e16},
}];
if(require.main===module) {
  const index=Number(process.env.K1_SCALED_CASE??0),item=cases[index];
  if(!item)throw new Error('unknown scaled fixture');
  const o={...probe.defaults,...item.options,verifyExit:true};
  console.log('FIXTURE',item.name);
  console.log('PASS surface:',JSON.stringify(deep.surface(o,probe.finish)));
  if(!process.env.K1_COMMA_SKIP_FRAME)console.log('PASS frames:',JSON.stringify(upper.frameCheck(probe.run(o))));
  const r=probe.traced(o);console.log('PASS native:',JSON.stringify(audit.check(r,item.working)));
  if(process.env.K1_COMMA_UNOBSERVED)console.log('PASS unobserved:',keyboard.compareUnobserved(JSON.parse(JSON.stringify(r.calc)),r.options,probe.finish));
}
module.exports={cases};
