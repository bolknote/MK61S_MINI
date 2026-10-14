'use strict';
// Conservative ORIGINAL ROM memory-write/read masks for one observed IP.
// Take both L alternatives of conditional microinstructions. No model or
// calculator mutations. A mask is conditional on THIS command/calendar.
const roms=require('/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs');
const cache=new Map();
function masks(chip,ip) {
  const key=chip+':'+ip;if(cache.has(key))return cache.get(key);
  const rom=roms[{ik1302:'ИК1302',ik1303:'ИК1303',ik1306:'ИК1306'}[chip]];
  const word=rom.команды[ip],read=[],write=[];
  for(let j=0;j<42;j++) {
    const nine=Math.floor(j/9);
    let sync=nine<3?word&127:nine===3?(word>>>7)&127:(word>>>14)&255;
    if(nine===4&&sync>31)sync=95;
    const sub=j<6?j:j<21?j%3+3:j%9;
    const code=rom.синхропрограммы[sync*9+sub]&63;
    const numbers=code>59?[(code-60)*2+60,(code-60)*2+61]:[code];
    if(numbers.some(n=>(rom.микрокоманды[n]>>>1)&1))read.push(j);
    if(numbers.some(n=>(rom.микрокоманды[n]>>>20)&1))write.push(j);
  }
  const result={read,write};cache.set(key,result);return result;
}
module.exports={masks};
