#!/usr/bin/env node
'use strict';
// Detached PRIMARY keyboard/control timing, not a calculator state import.
// Begin at one genuine native idle endpoint. Include the frozen press/frame
// key-down/release cadence instead of forcing an accepted9C page.
const assert=require('node:assert/strict');
const {run:prepare}=require('./cache-bc-head93-second-first-native.cjs');
const {pagesAt,auditConnected,sourceRoot}=require('./cache-bc-head93-packet-canonical-plan.cjs');
const model=require('./cache-bc-head93-primary-word-model.cjs');
const names=['Z','T','X1','U','V','W','Q','P7','P8','P9','P10','aux0','aux1','X','Y'];
const numeric=p=>Array.from({length:12},(_,j)=>p[1+3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const ordinary=p=>Array.from({length:12},(_,j)=>p[3*j]).reverse().map(n=>n.toString(16).toUpperCase()).join('');
const FIRST='007012345678',SECOND='007024681357';
const pins=n=>n<10?[n+2,1]:[n-3,8];
function keyCall(inlet,operand,lead=0,{kind='rcl',consumeP7=false,preserved=null}={}) {
  let a=model.clone(inlet.state),here=inlet.here,words=0;
  const pages=inlet.pages.map(p=>p.slice()),route=[],reads=[],numericReads=[],writers=[];
  let started=false,ended=false,firstDecode=null,held=true;
  const schedule=['cx','enter','swap','digit'].includes(kind)?[{count:lead,pins:[0,0]},
    {count:560,pins:kind==='cx'?[10,8]:kind==='swap'?[6,8]:kind==='digit'?pins(operand):[11,8]},{count:14*560,pins:[0,0]},
    {count:lead?30-lead:0,pins:[0,0]}]:[{count:lead,pins:[0,0]},
    {count:560,pins:kind==='lastx'?[11,9]:kind==='nop'?[10,9]:kind==='store'?[6,9]:[8,9]},{count:13*560,pins:[0,0]},
    {count:560,pins:kind==='lastx'?[11,8]:pins(operand)},{count:13*560,pins:[0,0]},
    {count:2*560,pins:[0,0]},
    {count:lead?30-lead:0,pins:[0,0]}]; // 28+2 frames; explicit lead+tail30.
  for(const part of schedule)for(let j=0;j<part.count;j++) {
    const ip=model.ip(a),opcode=a.r[30]+16*a.r[33];
    if(!started&&ip===0x9C&&opcode===(kind==='cx'?0x0D:kind==='enter'?0x0E:kind==='swap'?0x14:kind==='nop'?0x54:kind==='digit'?operand:kind==='lastx'?0x0F:(kind==='store'?0x40:0x60)+operand)) {
      started=true;firstDecode={word:words,owner:names[here],state:model.clone(a),pages:pages.map(p=>p.slice()),pins:part.pins};
    }
    if(started&&!ended) {
      if([0x9C,0x9E,0xEE,0xD6,0xE7,0xA8,0xA3].includes(ip))route.push([ip,names[here],words]);
      if(ip===0xD6)reads.push({reg:(here+12)%15,raw:ordinary(pages[here])});
      if(ip===0xEE)numericReads.push({word:names[here],raw:numeric(pages[here])});
      if([0xE7,0xA8,0xA3,0xD4,0xBC].includes(ip))writers.push([ip,names[here]]);
      if(ip===0xBE)ended=true;
    }
    const out=model.step(a,...part.pins,pages[(here+1)%15]);
    const writtenHere=here;
    pages[here]=out.out;a=out.state;here=(here+1)%15;words++;
    if(preserved?!preserved(pages,{state:a,ip,writtenWord:names[writtenHere],word:words-1}):
      ((!consumeP7&&numeric(pages[7])!==SECOND)||numeric(pages[10])!==FIRST||ordinary(pages[9])!==SECOND))held=false;
  }
  return {state:a,pages,here,words,firstDecode,route,reads,numericReads,writers,held,ended};
}
function compact(v) {return {decoded:v.firstDecode?{offset:v.firstDecode.word,owner:v.firstDecode.owner}:null,
  held:v.held,ended:v.ended,reads:v.reads,numericReads:v.numericReads,writers:v.writers,
  markers:names.filter((_,j)=>v.pages[j][22]===15),
  words:Object.fromEntries(names.map((n,j)=>[n,numeric(v.pages[j])]))};}
function run() {
  const data=prepare({proof:true}),endpoint=data.nativeEndpoints['packet-second-read-output'];
  auditConnected(data,['packet-second-first1']);
  const inlet={state:endpoint.fullBefore.ik1302,pages:pagesAt(data,endpoint),here:names.indexOf(endpoint.numericOwner[0].split(':')[1])};
  const actual=data.windows['packet-second-first1'][0],control=keyCall(inlet,4);
  assert.equal(control.firstDecode.owner,actual.numericOwner[0].split(':')[1]);
  assert.equal(endpoint.word+control.firstDecode.word,actual.word);
  for(const field of ['r','m','st','s','s1','l','t','carry'])
    assert.deepEqual(control.firstDecode.state[field],actual.fullBefore.ik1302[field],field);
  console.log('PASS PRIMARY keyboard prefix from one real endpoint to actual rejected9C,',
    control.firstDecode.word,'calculated words, all primary fields match. NOT ALL5.');
  const wanted=keyCall(inlet,6);
  const second=wanted.held?keyCall(wanted,6):null;
  // Only the five IR84-compatible idle residues of the proved30-word
  // inlet period. This is finite control-calendar analysis, not a key sweep.
  const phases=[0,6,12,18,24].map(lead=>({lead,...compact(keyCall(inlet,4,lead))}));
  const adapted=keyCall(inlet,4,6); // genuine calculated headerFFF/P9, numbers held.
  const p9Calls=[];let current=adapted;
  const template=actual.fullBefore.ik1302;
  const steps=[{reg:7,frame:'X1'},{reg:7,frame:'X1'},{reg:3,frame:'aux0'},
    {reg:4,frame:'Y'},{reg:4,frame:'Y'},{cxClear:'W'},{reg:4,frame:'Y'},
    {reg:2,frame:'aux0'},{reg:2,frame:'aux0'},{reg:2,frame:'aux0'},
    {cxClear:'X1'},{reg:2,frame:'aux0'}];
  for(const target of steps) {
    if(target.cxClear) {
      if(current.pages[names.indexOf(target.cxClear)][22]!==15)continue;
      let chosen=null;
      for(const lead of [0,6,12,18,24]) {
        const next=keyCall(current,0,lead,{kind:'cx'});
        if(next.held&&next.ended&&next.pages[names.indexOf(target.cxClear)][22]!==15){chosen={lead,next};break;}
      }
      if(!chosen){p9Calls.push({target,failed:true,...compact(current)});break;}
      current=chosen.next;p9Calls.push({target,kind:'cx',lead:chosen.lead,...compact(current)});
      continue;
    }
    const entries=names.map((_,j)=>j).filter(j=>current.pages[j][31]===15?current.pages[j][34]>=1:current.pages[j][34]>=7);
    const operands=[...new Set(entries.map(entry=>{
      const root=sourceRoot(current.pages,template,6,entry);
      return root===null?null:(target.reg+11-root+30)%15;
    }).filter(x=>x!==null))];
    let chosen=null,attempts=0;
    candidateLoop: for(const operand of operands)for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,operand,lead);attempts++;
      const firstFrame=next.writers.find(([ip])=>ip===0xE7);
      if(next.held&&next.ended&&next.reads[0]?.reg===target.reg&&firstFrame?.[1]===target.frame) {
        chosen={operand,lead,next};break candidateLoop;
      }
      if(chosen)break;
    }
    if(!chosen){p9Calls.push({target,operands,attempts,failed:true,...compact(current)});break;}
    current=chosen.next;p9Calls.push({target,operand:chosen.operand,lead:chosen.lead,attempts,...compact(current)});
    if(names.filter((_,j)=>current.pages[j][22]===15).join(',')==='P8')break;
  }
  const retained=[];
  if(names.filter((_,j)=>current.pages[j][22]===15).join(',')==='P8') {
    readerLoop:for(const lead of [0,6,12,18,24]) {
      const first=keyCall(current,0,lead,{kind:'lastx'});
      if(!first.held||!first.ended||first.numericReads[0]?.word!=='P10'||numeric(first.pages[11])!==FIRST)continue;
      retained.push({kind:'lastx',lead,...compact(first)});
      const acceptable=names.map((_,j)=>j).filter(j=>first.pages[j][31]===15?first.pages[j][34]>=1:first.pages[j][34]>=7);
      const ops=[...new Set(acceptable.map(entry=>sourceRoot(first.pages,template,4,entry))
        .filter(root=>root!==null).map(root=>(7+11-root+30)%15))];
      for(const op of ops)for(const tailLead of [0,6,12,18,24]) {
        const stored=keyCall(first,op,tailLead,{kind:'store'});
        if(stored.held&&stored.ended&&ordinary(stored.pages[10])===FIRST) {
          retained.push({kind:'store-first-R7',operand:op,lead:tailLead,...compact(stored)});break readerLoop;
        }
      }
      break;
    }
  }
  const consume=[];
  if(current.held) {
    let header=null;
    for(const lead of [0,6,12,18,24]) {
      const next=keyCall(current,4,lead);
      if(next.held&&next.writers.some(([ip,n])=>ip===0xA3&&n==='U')){header={lead,next};break;}
    }
    if(header) {
      consume.push({kind:'header-U',operand:4,lead:header.lead,...compact(header.next)});
      current=header.next;
      for(const lead of [0,6,12,18,24]) {
        const first=keyCall(current,0,lead,{kind:'lastx',consumeP7:true});
        if(first.held&&first.ended&&first.numericReads[0]?.word==='P10'&&
          names.some((_,j)=>j!==10&&numeric(first.pages[j])===FIRST)) {
          consume.push({kind:'lastx-consumes-P7',lead,...compact(first)});
          const acceptable=names.map((_,j)=>j).filter(j=>first.pages[j][31]===15?first.pages[j][34]>=1:first.pages[j][34]>=7);
          const ops=[...new Set(acceptable.map(entry=>sourceRoot(first.pages,template,4,entry))
            .filter(root=>root!==null).map(root=>(7+11-root+30)%15))];
          outputLoop:for(const op of ops)for(const tailLead of [0,6,12,18,24]) {
            const stored=keyCall(first,op,tailLead,{kind:'store',consumeP7:true});
            if(stored.held&&stored.ended&&ordinary(stored.pages[10])===FIRST) {
              consume.push({kind:'store-first-R7',operand:op,lead:tailLead,...compact(stored)});break outputLoop;
            }
          }
          break;
        }
      }
    }
  }
  console.log(JSON.stringify({control:compact(control),zeroPort9:compact(wanted),
    repeat:second?compact(second):null,phases,p9Calls,retained,consume,boundary:'whole key/release PRIMARY planning; native source/calendar and ALL5 verification required; consuming read NOT a retained two-slot cycle'}));
}
function auditPositive() {
  const data=prepare({proof:true,readFirst:true}),endpoint=data.nativeEndpoints['packet-second-read-output'];
  let current={state:endpoint.fullBefore.ik1302,pages:pagesAt(data,endpoint),here:names.indexOf(endpoint.numericOwner[0].split(':')[1])};
  const protocol=[['adapter',4,6],['V',10,0],['W',10,0],['Y',6,0],['T',7,0],['X1',7,0],
    ['Wzero',0,0,'cx'],['X1zero',4,0],...Array.from({length:4},(_,i)=>['flush'+(i+1),5,0]),
    ['read',0,0,'lastx'],['output',10,0,'store']];
  let calculated=0;
  for(const [suffix,operand,lead,kind='rcl'] of protocol) {
    const label='packet-second-first-'+suffix,next=keyCall(current,operand,lead,{kind});
    assert.ok(next.held,label+' numerical invariants');
    const native=data.nativeEndpoints[label];
    assert.equal(endpoint.word+calculated+next.words,native.word,label+' exact whole key/idle schedule');
    for(const field of ['r','m','st','s','s1','l','t','carry'])
      assert.deepEqual(next.state[field],native.fullBefore.ik1302[field],label+'/'+field);
    assert.deepEqual(next.pages,pagesAt(data,native),label+' all15 primary ring pages/all3 lanes');
    assert.equal(names[next.here],native.numericOwner[0].split(':')[1]);
    current=next;calculated+=next.words;
  }
  assert.equal(calculated,226830);assert.equal(ordinary(current.pages[10]),FIRST);
  console.log('PASS EXACT PRIMARY whole keyboard/idle schedule',calculated,'calculated words, '
    +'14 endpoint checks/all primary fields+15 ring pages. Two hidden numbers held, R6=SECOND/R7=FIRST. '
    +'No snapshot import or model repairs; NOT ALL5/full original preparation replay.');
}
if(require.main===module)process.argv.includes('--positive')?auditPositive():run();
module.exports={keyCall,auditPositive};
