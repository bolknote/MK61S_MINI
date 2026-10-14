#!/usr/bin/env node
'use strict';
// Follow physical ring positions in a separate shadow map. Only native
// press/inputNumber/runFrames change calculator state. Micro-order hooks
// record writes; they do not alter their operands, results, or ROM.
const assert = require('node:assert/strict');
const {MK61} = require('./paused_keyboard_state.cjs');
const hex = n => n.toString(16).toUpperCase();
const word = a => Array.from({length:12}, (_,i) => hex(a[34-3*i])).join('');
const locations = [
  [1,41],[1,83],[1,125],[1,167],[1,209],[1,251],
  [2,41],[2,83],[2,125],[2,167],[2,209],[2,251],
  [3,41],[4,41],[5,41],
];
// These names identify circulating positions, not the current contents.
// At frame boundary phase 1 this agrees with the reference's stack map
// [14,13,12,8,9] for X1,X,Y,Z,T and the documented hidden-word map.
const names = ['marker','control','P7','P8','P9','P10',
  'W','Q','Z','T','U','V','Y','X','X1'];

function trace(calc, action, options={}) {
  assert.equal(calc.ir2a.tickIndex, 84, 'initialize only at frame phase 1');
  const chips = [null,calc.ir2a,calc.ir2b,calc.ik1302,calc.ik1303,calc.ik1306];
  const tags = chips.map(c => c && new Array(c.memory.length));
  for (let page=0;page<15;page++) {
    const [chip,end] = locations[page];
    for (let i=0;i<42;i++) tags[chip][end-41+i] = {
      slot:names[page], nibble:i, lastWrite:null,
      value:chips[chip].memory[end-41+i],
    };
  }
  const originalTick = calc.tick, originals = [], activeIp = {};
  let ticks = 0, acNumber = 0, lastEvent = null, acRoute = null;
  let started = options.startIp === undefined;
  const events = [], writes = [], primitives = [];
  const eventIps=new Set([0xAC,0xEE,0xDE,...(options.extraIps||[])]);
  for (const chipId of [3,4,5]) {
    const chip = chips[chipId], original = chip.executeMicroOrder;
    originals.push([chip,original]);
    chip.executeMicroOrder = function(number,acc) {
      if (number === 24) {
        const tag = tags[chipId][this.tickIndex];
        const before=tag.value;
        tag.lastWrite = {chip:chipId, ip:activeIp[chipId],
          tick:this.tickIndex, command:Math.floor(ticks/42), value:this.s};
        tag.value = this.s;
        // Optional passive streaming audit avoids retaining millions of
        // writes for long composed protocols. It may inspect, never edit.
        options.onWrite?.({slot:tag.slot,nibble:tag.nibble,before,...tag.lastWrite});
        if(options.allWrites)
          writes.push({slot:tag.slot,nibble:tag.nibble,before,...tag.lastWrite});
        else if (tag.nibble === 34 && this.s !== 0 && this.s !== 9)
          writes.push({slot:tag.slot,...tag.lastWrite});
      }
      return original.call(this,number,acc);
    };
  }
  calc.tick = function() {
    const k=this.ik1302.tickIndex, j=this.ir2a.tickIndex;
    if (k === 0) {
      for (const id of [3,4,5]) activeIp[id]=chips[id].r[36]+16*chips[id].r[39];
      const c=this.ik1302, ip=c.r[36]+16*c.r[39];
      if(ip===options.startIp) started=true;
      if (lastEvent) { lastEvent.nextIp=ip; lastEvent=null; }
      if (ip === 0xAC) { acNumber++; acRoute=[]; }
      // Collapse only the proved field-preserving E5 waits. Other repeated
      // instructions may transform data and must remain in the trace.
      if (acRoute && acRoute.length<160 && !(ip===0xE5 && acRoute.at(-1)===ip))
        acRoute.push(ip);
      if (ip === 0xC7 || ip === 0xC8) primitives.push(ip);
      // Optional log-only filtering keeps long composed native runs compact.
      if (started && eventIps.has(ip) && (!options.eventFilter || options.eventFilter(ip))) {
        const header = tags[3][34];
        assert.equal(header.nibble,34, 'physical lane/field is preserved');
        assert.equal(header.value,c.memory[34], 'all ring header writes accounted for');
        const event={ip,command:Math.floor(ticks/42),acNumber,
          slot:header.slot,raw:word(c.memory),lastWrite:header.lastWrite,
          r0:c.r[0],r1:c.r[1],r2:c.r[2],r35:c.r[35],
          pc:c.r[31]+16*c.r[34],st32:c.stack[32],st35:c.stack[35],
          s1:c.s1,sp:[0,1,2].map(i=>c.stack[36+i]+16*c.stack[39+i])};
        if(options.fullState) Object.assign(event,{r:c.r.slice(),st:c.stack.slice(),
          m:c.memory.slice(),s:c.s,l:c.l,t:c.t,carry:c.carry,keyX:c.keyX,keyY:c.keyY});
        if(options.otherChipsAt?.(event)) event.otherChips=Object.fromEntries([4,5].map(id=>{
          const chip=chips[id];
          return [id,{ip:activeIp[id],slot:tags[id][34].slot,
            r:chip.r.slice(),st:chip.stack.slice(),m:chip.memory.slice(),
            s:chip.s,s1:chip.s1,l:chip.l,t:chip.t,carry:chip.carry,
            keyX:chip.keyX,keyY:chip.keyY}];
        }));
        // Read-only, phase-independent physical ring snapshot. It never calls
        // a synchronizing register/program getter or advances the machine.
        if(options.ringAt?.(event)) {
          event.ring=Object.fromEntries(names.map(name=>[name,new Array(42)]));
          for(const id of [1,2,3,4,5]) for(let n=0;n<tags[id].length;n++) {
            const tag=tags[id][n],value=chips[id].memory[n];
            assert.equal(value,tag.value,'shadow ring accounts for every write');
            event.ring[tag.slot][tag.nibble]=value;
          }
        }
        if (ip===0xAC) event.route=acRoute;
        events.push(event);
        lastEvent=event;
      }
    }
    // Simultaneous ring transfer. IK1302.closeRing overrides its initial
    // input from the previous tick with the current IR2b output.
    const next = [tags[2][j],tags[3][k],tags[4][k],tags[5][k],tags[1][j]];
    originalTick.call(this);
    [tags[3][k],tags[4][k],tags[5][k],tags[1][j],tags[2][j]] = next;
    ticks++;
  };
  try { action(calc); } finally {
    calc.tick=originalTick;
    for (const [chip,original] of originals) chip.executeMicroOrder=original;
  }
  return {events,writes,primitives,display:calc.displayText(),pc:calc.programCounter()};
}

function aligned(calc) {
  for (let i=0;i<3 && calc.ir2a.tickIndex!==84;i++) calc.runFrames(1);
  assert.equal(calc.ir2a.tickIndex,84);
  return calc;
}

function run() {
  const cases = [];
  for (const value of ['12345672','-1E-3']) {
    const calc=new MK61();
    calc.pressSequence(['БП','5','8']);
    calc.inputNumber(value,{clear:true}).pressSequence(['В↑','1']);
    const result=trace(aligned(calc),c=>c.press('+'));
    const ee=result.events.find(e=>e.ip===0xEE && e.acNumber===1);
    assert.ok(ee);
    assert.equal(ee.slot,'X');
    assert.ok(['0','9'].includes(ee.raw[0]));
    assert.deepEqual(result.primitives,[]);
    cases.push({name:'ordinary_'+value,...result});
  }
  return cases;
}

if (require.main === module) {
  const cases=run();
  if (process.argv.includes('--json')) console.log(JSON.stringify(cases));
  else for (const c of cases) console.log(JSON.stringify({name:c.name,
    reads:c.events.filter(e=>e.ip===0xEE),abnormalHeaderWrites:c.writes.length}));
}
module.exports={MK61,trace,aligned,run};
