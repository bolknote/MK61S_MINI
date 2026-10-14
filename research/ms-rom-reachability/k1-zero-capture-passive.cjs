#!/usr/bin/env node
'use strict';
// Fresh original reference + fixed public-key half-pair. Tags and snapshots
// are passive evidence only, never loaded into a native calculator.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const cap=require('./k1-bank-v-capture.cjs'),candidate=require('./arbitrary-bank-pair-zero-capture.cjs');
const uvReader=require('./k1-zero-uv-retained-reader.cjs');
const {initialTags}=require('./cache-bc-head93-native-carriers.cjs');
const model=require('./cache-bc-head93-numeric-all5-model.cjs');
const {snapshot}=require('./k1-zq-header-collision.cjs');
const chips=[null,'ir2a','ir2b','ik1302','ik1303','ik1306'];
const full=c=>Object.fromEntries(chips.slice(1).map(n=>{const p=c[n];return[n,{m:p.memory.slice(),
  tick:p.tickIndex,input:p.input,output:p.output,...(n.startsWith('ik')?{r:p.r.slice(),st:p.stack.slice(),
    s:p.s,s1:p.s1,l:p.l,t:p.t,carry:p.carry,keyX:p.keyX,keyY:p.keyY}:{})}];}));
const tagMap=t=>Object.fromEntries(chips.slice(1).map((n,i)=>[n,t[i+1].slice()]));
const pins={'Сx':[10,8],'В↑':[11,8],'+':[2,8],'П→X':[8,9],'X→П':[6,9],
  'K':[10,9],'-':[3,8],'ВП':[9,8],'0':[2,1],'4':[6,1],'F':[11,9],',':[7,8],'↔':[6,8]};
function run(options={},variant='capture'){
  assert.ok(['capture','uv-reader','u-reserve','canonical-u-reserve'].includes(variant));
  const isReader=variant==='uv-reader',isReserve=variant==='u-reserve',isCanonical=variant==='canonical-u-reserve',
    body=isCanonical?require('./k1-uv-u-canonical-reserve.cjs'):
      isReserve?require('./k1-uv-u-lastx-reserve.cjs'):isReader?uvReader:candidate,
    activeStage=isCanonical?'canonical-abs':isReserve?'cache-u':isReader?'uv-read':'zero-capture-store-v';
  const o={incoming:'-1.2345678E42',p3:'777',phaseOffset:2,
    values:['811','822','-9.8765432E23','4.44E12'],fullUpper:['9011','9022','9033','9044'],...options};
  const files=['/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs','/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs',
    ...['ik1302_symbolic.py','analyze_gates.py','audit_ms_rom_control.py','k1-formatter-entry-audit.py'].map(n=>path.join(__dirname,n))];
  const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
  const frozen=Object.fromEntries(files.map(p=>[p,hash(p)])),c=cap.prepare(o),plain=cap.prepare(o);
  assert.deepEqual(snapshot(c),snapshot(plain));
  const {tags,cells}=initialTags(c),entry={word:0,fullBefore:full(c),tagsBefore:tagMap(tags)};
  const beforeCore=model.make(entry),originalWords=Array.from({length:15},(_,i)=>model.physical(beforeCore,cells,'register','R'+i.toString(16).toUpperCase()))
    .concat(['U','V','W','Q','P7','P8','P9','P10'].map(w=>model.physical(beforeCore,cells,'Ms',w)));
  assert.equal(new Set(originalWords).size,23);
  const originalTick=c.tick,windows={[activeStage]:[]},schedule=[];
  let word=-1,stage='phase',active=false,done=false,record=null;
  const owners=()=>[...new Set(tags[3].filter((_,j)=>j%3===1).map(id=>cells[id].area+':'+cells[id].word))];
  c.tick=function(){
    const at=chips.map((n,i)=>i?this[n].tickIndex:0);
    if(at[3]===0){
      word++;const p=this.ik1302,ip=p.r[36]+16*p.r[39],opcode=p.r[30]+16*p.r[33];
      if(!done&&stage===activeStage&&ip===0x9C&&opcode===(isCanonical?0x31:isReserve?0x27:isReader?0x25:0x40))active=true;
      if(active){record={word,ip,stage,numericOwner:owners(),fullBefore:full(this),tagsBefore:tagMap(tags),emitted:[]};
        windows[activeStage].push(record);}
    }
    const old=at.map((j,i)=>i?tags[i][j]:0),result=originalTick.call(this);
    const incoming=[0,old[5],old[1],old[2],old[3],old[4]];
    for(let i=1;i<=5;i++)tags[i][at[i]]=incoming[i];
    if(active){record.emitted.push(this.ik1302.output);
      if(this.ik1302.tickIndex===0){record.fullAfter=full(this);record.tagsAfter=tagMap(tags);
        if(record.ip===0xBE){active=false;done=true;}}}
    return result;
  };
  let proxy;
  proxy=new Proxy(c,{get(target,n){
    assert.ok(['pressSequence','runFrames'].includes(n),'protocol attempted private calculator read '+String(n));
    return(...args)=>{
      if(n==='pressSequence')for(const key of args[0]){assert.ok(pins[key]);schedule.push({stage,count:560,key:pins[key]},
        {stage,count:560,key:[0,0]});}
      else schedule.push({stage,count:args[0]*560,key:[0,0]});
      target[n](...args);return proxy;
    };
  },set(){throw Error('protocol state assignment forbidden');}});
  try{body.operation(proxy,o,s=>{stage=s;});}finally{c.tick=originalTick;}
  assert.ok(done,'last native reader/STORE window completed');
  const end={word:word+1,fullBefore:full(c),tagsBefore:tagMap(tags),numericOwner:owners()};
  assert.equal(end.word,schedule.reduce((n,s)=>n+s.count,0));
  body.operation(plain,o);
  assert.deepEqual(snapshot(c),snapshot(plain),'full native key-only observer-free mirror');
  const endCore=model.make(end),logicalMap={X:'Y',Y:'Z',Z:'T',T:'X1',X1:'X'};
  if(isReader||isReserve||isCanonical){
    const banks=Array.from({length:15},(_,i)=>model.physical(endCore,cells,'register','R'+i.toString(16).toUpperCase()))
      .concat(['U','V','W','Q','P7','P8','P9','P10'].map(w=>model.physical(endCore,cells,'Ms',w)));
    assert.deepEqual(banks,originalWords,'all 23 bank words retained at original addresses');
    if(isCanonical){
      assert.equal(model.physical(endCore,cells,'stack','X'),originalWords[15]);
      assert.equal(model.physical(endCore,cells,'stack','Y'),originalWords[15]);
      const words=['U','V','W','Q','P7','P8','P9','P10'].map(w=>model.physical(endCore,cells,'Ms',w))
        .concat(['X','Y','Z','T','X1'].map(w=>model.physical(endCore,cells,'stack',w)),
          ['aux0','aux1'].map(w=>model.physical(endCore,cells,'unclassified',w)));
      assert.deepEqual(words.flatMap((w,i)=>w[4]==='F'?[i]:[]),[13],'canonical aux0 only');
    }else if(isReserve){
      assert.equal(model.physical(endCore,cells,'stack','X'),originalWords[15]);
      assert.equal(model.physical(endCore,cells,'stack','Y'),originalWords[15]);
      assert.equal(model.physical(endCore,cells,'stack','Z'),'0040F0000000');
    }else assert.equal(model.physical(endCore,cells,'stack','T'),originalWords[16]);
    if(!isCanonical)assert.equal(model.physical(endCore,cells,'stack','X1'),originalWords[15]);
  }else{
    assert.equal(model.physical(endCore,cells,'register','R0'),originalWords[16]);
    assert.equal(model.physical(endCore,cells,'stack','X1'),originalWords[0]);
    assert.equal(model.physical(endCore,cells,'stack','T'),'0000F0000000');
  }
  const finalWords=Array.from({length:15},(_,i)=>model.physical(endCore,cells,'register','R'+i.toString(16).toUpperCase()))
    .concat(['U','V','W','Q','P7','P8','P9','P10'].map(w=>model.physical(endCore,cells,'Ms',w)),
      ['X','Y','Z','T','X1'].map(w=>model.physical(endCore,cells,'stack',w)));
  assert.ok(originalWords.every(w=>finalWords.includes(w)));
  for(const [f,h] of Object.entries(frozen))assert.equal(hash(f),h);
  return{schema:isCanonical?'k1-uv-u-canonical-passive-v1':isReserve?'k1-uv-u-reserve-passive-v1':
    isReader?'k1-zero-uv-reader-passive-v1':'k1-zero-capture-passive-v1',metadata:{options:o,logicalMap,onlyPublicKeys:true,ALL5mirror:true,
    frozenSha256:frozen,originalWords,protocolWords:end.word,
    boundary:isCanonical?'native U stored/read from real LastX after clear, all 23 banks held, canonical marker only; no reverse writer/full K1':
      isReserve?'native full U in real LastX and X/T, all 23 banks held, false Y marker remains; no reverse writer/full K1':
      isReader?'native U/V copies in Z/T, all 23 original bank words retained, canonical marker; no reverse writer/full K1':
      'native preserving V->P0 half-pair, oldP0 retained in logicalT, marker logicalZ; no reverse write/clean exit/full K1'},
    cells,schedule,windows,endpoints:isCanonical?{'canonical-start':entry,'canonical-end':end}:
      isReserve?{'reserve-start':entry,'reserve-end':end}:
      isReader?{'reader-start':entry,'reader-end':end}:{'capture-start':entry,'capture-end':end}};
}
if(require.main===module){const d=run(process.argv[2]?JSON.parse(process.argv[2]):{}),dir=fs.mkdtempSync('/private/tmp/k1-zero-capture-'),
  out=path.join(dir,'native-proof.json');fs.writeFileSync(out,JSON.stringify(d),{flag:'wx'});
  console.log(JSON.stringify({output:out,sha256:crypto.createHash('sha256').update(fs.readFileSync(out)).digest('hex'),
    bytes:fs.statSync(out).size,metadata:d.metadata,activeWords:d.windows['zero-capture-store-v'].length}));}
module.exports={run};
