'use strict';
// Pure, read-only analysis of already captured data. No emulator imports or
// native execution. A bijection in one fixture is NOT a usable/full K1 proof.
const MS_SLOTS=Object.freeze(['U','V','W','Q','P7','P8','P9','P10']);
const M1_SLOTS=Object.freeze(['U','V','W','Q','P7','P8','P9','P10',
  'marker','control','X1','X','Y','Z','T']);
const RING_SLOTS=Object.freeze(['marker','control','X1','X','Y','Z','T',...MS_SLOTS]);
const PLACES=Object.freeze([...Array.from({length:15},(_,i)=>'reg.'+i.toString(16).toUpperCase()),
  ...MS_SLOTS.map(n=>'ms.'+n)]);

function requireValue(condition,message) {if(!condition)throw new TypeError(message);}
function integers(value,length,max,label) {
  requireValue(Array.isArray(value)&&value.length===length,label+' must have length '+length);
  requireValue(Array.from(value).every(n=>Number.isInteger(n)&&n>=0&&n<=max),label+' has an invalid value');
  return value.slice();
}
function words(value,label) {
  requireValue(Array.isArray(value)&&value.length===23,label+' must contain 23 words');
  requireValue(Array.from(value).every(w=>typeof w==='string'&&/^[0-9a-f]{12}$/i.test(w)),
    label+' words must contain exactly 12 hexadecimal tetras');
  return value.map(w=>w.toUpperCase());
}
function expectedPermutation(value) {
  if(value===undefined)return null;
  const result=integers(value,23,22,'expectedMapping');
  requireValue(new Set(result).size===23,'expectedMapping must be a bijection');
  return result;
}
function groups(values) {
  const result=new Map();
  values.forEach((word,index)=>{
    if(!result.has(word))result.set(word,[]);
    result.get(word).push(index);
  });
  return result;
}
function locations(indices) {return indices.map(i=>PLACES[i]);}
function compareField(before,after,length,max,labels) {
  if(before!==undefined)integers(before,length,max,'before protected field');
  if(after!==undefined)integers(after,length,max,'after protected field');
  if(before===undefined||after===undefined)return {status:'unverified_missing_snapshot',changes:[]};
  const changes=before.flatMap((value,i)=>value===after[i]?[]:
    [{index:i,field:labels[i],before:value,after:after[i]}]);
  return {status:changes.length?'damaged':'preserved_at_endpoints',changes};
}
function cycleReport(destinationToSource) {
  if(!destinationToSource)return {sourceToDestination:null,cycles:[]};
  const sourceToDestination=Array(23),seen=new Set(),cycles=[];
  destinationToSource.forEach((src,dst)=>{sourceToDestination[src]=dst;});
  for(let start=0;start<23;start++)if(!seen.has(start)) {
    const cycle=[];let at=start;
    while(!seen.has(at)){seen.add(at);cycle.push(PLACES[at]);at=sourceToDestination[at];}
    if(cycle.length>1)cycles.push(cycle);
  }
  return {sourceToDestination,cycles};
}
function inspectWrites(writes) {
  if(writes===undefined)return {status:'not_assessed',coverage:'unverified',changes:[]};
  requireValue(Array.isArray(writes),'writes must be an array');
  const changes=[];
  for(const w of writes) {
    requireValue(w&&RING_SLOTS.includes(w.slot),'write has an unknown slot');
    integers([w.nibble],1,41,'write nibble');integers([w.before,w.value],2,15,'write data');
    const field=w.nibble%3===2?'program':
      [36,39].includes(w.nibble)?'m1Service':[37,40].includes(w.nibble)?'m2Service':null;
    if(field&&w.before!==w.value)changes.push({field,slot:w.slot,nibble:w.nibble,
      before:w.before,after:w.value,...(w.command===undefined?{}:{command:w.command}),
      ...(w.chip===undefined?{}:{chip:w.chip}),...(w.ip===undefined?{}:{ip:w.ip})});
  }
  return {status:changes.length?'changes_observed':'no_changes_in_supplied_log',
    coverage:'unverified',changes};
}

/** Snapshot: {words: string[23], program?: byte[105],
 * services?: {m1?: tetra[30],m2?: tetra[30]}}.
 * Services are in RING_SLOTS order: M1[36,39], M2[37,40].
 * expectedMapping is destination-to-source, and is never inferred anew when supplied.
 */
function analyzeSnapshots({before,after,expectedMapping,writes}={}) {
  requireValue(before&&after,'before and after snapshots are required');
  const input=words(before.words,'before'),output=words(after.words,'after');
  const expected=expectedPermutation(expectedMapping),sources=groups(input),destinations=groups(output);
  const collisions=[...sources].filter(([,indices])=>indices.length>1)
    .map(([word,indices])=>({word,sourceIndices:indices,sourcePlaces:locations(indices)}));
  const missing=[],duplicates=[],foreign=[];
  for(const [word,indices] of sources) {
    const dst=destinations.get(word)??[];
    const entry={word,sourceIndices:indices,sourcePlaces:locations(indices),
      destinationIndices:dst,destinationPlaces:locations(dst)};
    if(dst.length<indices.length)missing.push({...entry,missingCount:indices.length-dst.length});
    if(dst.length>indices.length)duplicates.push({...entry,extraCount:dst.length-indices.length});
  }
  for(const [word,indices] of destinations)if(!sources.has(word))
    foreign.push({word,destinationIndices:indices,destinationPlaces:locations(indices)});
  const sameMultiset=missing.length===0&&duplicates.length===0&&foreign.length===0;
  const distinct=collisions.length===0,bijection=distinct&&sameMultiset;
  const destinationToSource=bijection?output.map(word=>sources.get(word)[0]):null;
  const mismatches=expected?output.flatMap((word,dst)=>word===input[expected[dst]]?[]:
    [{destination:PLACES[dst],destinationIndex:dst,source:PLACES[expected[dst]],
      sourceIndex:expected[dst],expectedWord:input[expected[dst]],actualWord:word}]):[];
  const protection={
    program:compareField(before.program,after.program,105,255,
      Array.from({length:105},(_,i)=>'program.'+i)),
    m1Service:compareField(before.services?.m1,after.services?.m1,30,15,
      RING_SLOTS.flatMap(n=>[n+'.M1[36]',n+'.M1[39]'])),
    m2Service:compareField(before.services?.m2,after.services?.m2,30,15,
      RING_SLOTS.flatMap(n=>[n+'.M2[37]',n+'.M2[40]'])),
  };
  const damaged=Object.values(protection).some(p=>p.status==='damaged');
  const protectionComplete=Object.values(protection).every(p=>p.status==='preserved_at_endpoints');
  const status=!distinct?'NON_DISTINCT_FIXTURE':!bijection?'DATA_LOSS_OR_DUPLICATION':
    damaged?'PROTECTED_FIELD_DAMAGE':expected&&mismatches.length?'FIXED_MAPPING_MISMATCH':
    !protectionComplete?'PERMUTATION_WITH_UNVERIFIED_PROTECTION':'PERMUTATION_INSTANCE_ONLY';
  return {
    kind:'k1-permutation-instance-analysis',status,
    fixture:{distinct,collisions},
    data:{sameMultiset,bijection,missing,duplicates,foreign,destinationToSource,
      ...cycleReport(destinationToSource),
      hasOrdinaryToMsEdge:bijection&&destinationToSource.slice(15).some(src=>src<15)},
    fixedMapping:{status:expected?(mismatches.length?'mismatch':'matches_this_fixture'):'not_supplied',
      expectedDestinationToSource:expected,originIdentifiable:distinct,mismatches},
    protection,transientProtection:inspectWrites(writes),
    operational:{workingExit:'not_checked',repeatability:'not_checked',numericDomain:'not_proved',
      keyboardOnly:'not_checked',observerNoninterference:'not_checked'},
    suitableForComposition:false,fullK1:false,
    limitation:'Endpoint evidence only; no operational, universal-domain, or full K1 claim.',
  };
}

/** Extract from an existing phase-independent ring snapshot. Does not read a calculator. */
function snapshotFromRing(ring) {
  requireValue(ring&&typeof ring==='object','ring snapshot is required');
  const r=Object.fromEntries(RING_SLOTS.map(n=>[n,integers(ring[n],42,15,'ring.'+n)]));
  const raw=(name,lane)=>Array.from({length:12},(_,i)=>r[name][lane+3*(11-i)]
    .toString(16).toUpperCase()).join('');
  return {words:[...M1_SLOTS.map(n=>raw(n,0)),...MS_SLOTS.map(n=>raw(n,1))],
    program:M1_SLOTS.flatMap(n=>Array.from({length:7},(_,step)=>{
      const hi=step===0?41:step*6-1;return r[n][hi]*16+r[n][hi-3];
    })),
    services:{m1:RING_SLOTS.flatMap(n=>[r[n][36],r[n][39]]),
      m2:RING_SLOTS.flatMap(n=>[r[n][37],r[n][40]])}};
}

/** Both events must be chosen explicitly by the caller. The after event is a
 * pre-command snapshot; only writes in [before.command, after.command) belong here. */
function analyzeTrace({beforeEvent,afterEvent,writes,expectedMapping}={}) {
  for(const [name,e] of [['beforeEvent',beforeEvent],['afterEvent',afterEvent]])
    requireValue(e&&Number.isSafeInteger(e.command)&&e.command>=0,name+' needs a command index');
  requireValue(afterEvent.command>=beforeEvent.command,'trace boundaries are reversed');
  if(writes!==undefined) {
    requireValue(Array.isArray(writes),'writes must be an array');
    for(const w of writes)requireValue(w&&Number.isSafeInteger(w.command)&&w.command>=0,
      'trace writes need command indices');
  }
  const selected=writes?.filter(w=>w.command>=beforeEvent.command&&w.command<afterEvent.command);
  return {...analyzeSnapshots({before:snapshotFromRing(beforeEvent.ring),
    after:snapshotFromRing(afterEvent.ring),expectedMapping,writes:selected}),
    boundaries:{beforeCommand:beforeEvent.command,afterCommand:afterEvent.command,
      writeInterval:'inclusive-before, exclusive-after'}};
}
module.exports={PLACES,MS_SLOTS,M1_SLOTS,RING_SLOTS,analyzeSnapshots,snapshotFromRing,analyzeTrace};
