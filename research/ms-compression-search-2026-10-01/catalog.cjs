'use strict';
// Read-only catalog scan using its existing mnemonic parser. All artifacts
// stay in this experiment; animation programs are not selected for a demo.
const fs=require('node:fs');
const path=require('node:path');
const ref='/Users/bolk/Projects/MK-61';
const {parseLordBssGame}=require(path.join(ref,'tests/emulator/lordbss.cjs'));
const {parseProgramText}=require(path.join(ref,'tests/emulator/mk61.cjs'));
function files(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(path.join(dir,e.name)):[path.join(dir,e.name)]);}
function ordinary(word){
  const t=[];for(let j=1;j<7;j++){t.push(word[j]&15,word[j]>>4);}
  const m=t.slice(0,8), sign=t[8], order=t.slice(9);
  if(m.some(d=>d>9)||![0,9].includes(sign)||order[0]>9||order[1]>9||![0,9].includes(order[2]))return false;
  return m.every(d=>d===0)||m[7]>0;
}
const programs=[], failures=[];
for(const file of files(path.join(ref,'games')).filter(p=>p.endsWith('.txt'))){
  try{
    const listing=parseLordBssGame(file), parsed=parseProgramText(listing.programText);
    if(parsed.diagnostics.length)throw new Error(parsed.diagnostics.join('; '));
    const raw=parsed.codes;
    if(!raw.length)continue;
    // Add the implicit final address 00 after a final direct transfer.
    if([0x51,0x53,0x57,0x59,0x5c,0x5e,0x58,0x5a,0x5b,0x5d].includes(raw.at(-1)))raw.push(0);
    const compatible=[];
    for(let shift=0;shift<7;shift++){
      if(raw.length+shift>63)continue;
      const output=Array(shift).fill(0).concat(raw);while(output.length%7)output.push(0);
      let n=0, eligible=0;
      for(let j=0;j<output.length;j+=7){n++;if(ordinary(output.slice(j,j+7)))eligible++;}
      if(eligible===n)compatible.push({shift,words:n,serviceBytes:Array.from({length:n},(_,j)=>output[j*7])});
    }
    programs.push({file,title:listing.title,bytes:raw.length,raw:Buffer.from(raw).toString('hex'),ordinaryLayouts:compatible});
  }catch(e){failures.push({file,error:e.message});}
}
const report={programs,failures,parsed:programs.length,failed:failures.length,
  ordinaryCompatible:programs.filter(p=>p.ordinaryLayouts.length),
  small:programs.filter(p=>p.bytes<=63).length};
fs.writeFileSync(path.join(__dirname,'catalog.json'),JSON.stringify(report,null,2)+'\n');
process.stdout.write(JSON.stringify({parsed:report.parsed,failed:report.failed,small:report.small,ordinaryCompatible:report.ordinaryCompatible},null,2)+'\n');
