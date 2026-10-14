'use strict';
// DETACHED numeric ROM interpreter, not a calculator/chip instance.
// Snapshots are model inputs only and NEVER written into a stock reference.
// Ordered micro-operations mirror the frozen ROM semantics; independently
// audited against native whole-word R/ST/M/scalar/output records by planner.
const rom=require('/Users/bolk/Projects/MK-61/tests/emulator/rom.cjs').ИК1302;
const fields=['r','m','st'];
function clone(a) {return {...a,...Object.fromEntries(fields.map(k=>[k,a[k].slice()]))};}
function ip(a) {return a.r[36]+16*a.r[39];}
function step(initial,keyX,keyY,incoming,sourceRom=rom) {
  const a=clone(initial),word=sourceRom.команды[ip(a)],out=[];
  const user=(word>>>16)&63;
  if(!user)a.t=0;
  let sync=0;
  for(let j=0;j<42;j++) {
    const nine=Math.floor(j/9),trio=Math.floor(j/3);
    if(j%9===0&&(nine===0||nine>=3)) {
      sync=nine===0?word&127:nine===3?(word>>>7)&127:(word>>>14)&255;
      if(nine===4&&sync>31) {a.r[37]=sync&15;a.r[40]=sync>>>4;sync=95;}
    }
    const sub=j<6?j:j<21?j%3+3:j%9;
    let number=sourceRom.синхропрограммы[sync*9+sub]&63;
    if(number>59)number=(number-60)*2+60+(a.l===0?1:0);
    const micro=sourceRom.микрокоманды[number],bit=i=>(micro>>>i)&1;
    if(bit(25)&&trio!==keyX-1)a.s1|=keyY;
    const source=[a.r[j],a.m[j],a.st[j],~a.r[j]&15,a.l===0?10:0,
      a.s,4,a.s,~a.s&15,a.s1,6,1];
    let alpha=0,beta=0,gamma=0;
    for(let i=0;i<12;i++)if(bit(i)){if(i<=6)alpha|=source[i];else beta|=source[i];}
    if(user) {if(keyY===0)a.t=0;}
    else if(trio===keyX-1&&keyY>0){a.s1=keyY;a.t=1;}
    if(bit(12))gamma|=a.l&1;
    if(bit(13))gamma|=~a.l&1;
    if(bit(14))gamma|=~a.t&1;
    const sum=alpha+beta+gamma,sigma=sum&15;a.carry=(sum>>>4)&1;
    const apply=n=>{
      const p=(j+1)%42,q=(j+2)%42;
      switch(n) {
        case 15:a.r[j]=a.r[(j+3)%42];break;
        case 16:a.r[j]=sigma;break;
        case 17:a.r[j]=a.s;break;
        case 18:a.r[j]|=a.s|sigma;break;
        case 19:a.r[j]=a.s|sigma;break;
        case 20:a.r[j]|=a.s;break;
        case 21:a.r[j]|=sigma;break;
        case 22:a.r[(j+41)%42]=sigma;break;
        case 23:a.r[(j+40)%42]=sigma;break;
        case 24:a.m[j]=a.s;break;
        case 25:a.l=a.carry;break;
        case 26:a.s=a.s1;break;
        case 27:a.s=sigma;break;
        case 28:a.s=a.s1|sigma;break;
        case 29:a.s1=sigma;break;
        case 30:break;
        case 31:a.s1|=sigma;break;
        case 32:a.st[q]=a.st[p];a.st[p]=a.st[j];a.st[j]=sigma;break;
        case 33:{const x=a.st[j];a.st[j]=a.st[p];a.st[p]=a.st[q];a.st[q]=x;break;}
        case 34:{const x=a.st[j],y=a.st[p],z=a.st[q];a.st[j]=sigma|y;a.st[p]=x|z;a.st[q]=y|x;break;}
        default:throw Error('unknown micro destination '+n);
      }
    };
    if(!((word>>>22)&1)||nine===4) {
      const selector=bit(15)+2*bit(16)+4*bit(17);
      if(selector)apply(selector+14);
      if(bit(18))apply(22);if(bit(19))apply(23);
    }
    if(bit(20))apply(24);if(bit(21))apply(25);
    for(let i=0;i<3;i++){const selector=bit(22+2*i)+2*bit(23+2*i);if(selector)apply(selector+25+3*i);}
    out.push(a.m[j]);a.m[j]=incoming[j];
  }
  return {state:a,out};
}
module.exports={clone,ip,step};
