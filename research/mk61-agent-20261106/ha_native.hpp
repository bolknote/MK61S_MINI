#pragma once
// Bounded, allocation-free frontend for the research HEX harness.
// This code expands arguments and relocates labels; it does not choose a program.
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <cctype>

namespace mk61ha {
constexpr unsigned BodyMax=512, ProgramMax=105, PoolMax=256, NumberMax=20;
struct Pool { char values[PoolMax][NumberMax]{}; unsigned count=0; };
struct State { std::uint8_t body[BodyMax]{}; unsigned size=0; Pool pool; };
struct Relocation { std::uint8_t position,label; };
struct Workspace { std::uint16_t labels[256]; Relocation relocations[ProgramMax]; unsigned count=0; };
enum class Action : int { Write=1, Patch=2, Run=3, Trace=4, Done=5 };

inline bool word(unsigned char c) { return c>=128 || std::isalnum(c) || c=='_'; }
inline bool digit(char c) { return c>='0' && c<='9'; }
inline int hex(char c) { return digit(c)?c-'0':c>='A'&&c<='F'?c-'A'+10:c>='a'&&c<='f'?c-'a'+10:-1; }

inline int canonical(const char *s,unsigned n,char *out) {
  bool negative=false; unsigned at=0;
  if(at<n && (s[at]=='-'||s[at]=='+')) { negative=s[at]=='-'; ++at; }
  unsigned first=at; while(at<n && digit(s[at])) ++at;
  unsigned integerEnd=at, fractionStart=at, fractionEnd=at;
  if(at<n && s[at]=='.') { fractionStart=++at; while(at<n && digit(s[at])) ++at; fractionEnd=at; }
  if(at!=n || (integerEnd==first && fractionEnd==fractionStart)) return -1;
  while(first<integerEnd && s[first]=='0') ++first;
  while(fractionEnd>fractionStart && s[fractionEnd-1]=='0') --fractionEnd;
  bool zero=first==integerEnd && fractionEnd==fractionStart; unsigned used=0;
  if(negative && !zero) out[used++]='-';
  if(first==integerEnd) out[used++]='0';
  else for(unsigned i=first;i<integerEnd;++i) { if(used+1>=NumberMax)return -1;out[used++]=s[i]; }
  if(fractionEnd>fractionStart) {
    if(used+1>=NumberMax)return -1;out[used++]='.';
    for(unsigned i=fractionStart;i<fractionEnd;++i) { if(used+1>=NumberMax)return -1;out[used++]=s[i]; }
  }
  out[used]=0;return 0;
}

inline bool brand(const char *p,unsigned &length) {
  const unsigned char *s=reinterpret_cast<const unsigned char *>(p);
  if(s[0]!=0xD0 || (s[1]!=0x9C&&s[1]!=0xBC) || s[2]!=0xD0 || (s[3]!=0x9A&&s[3]!=0xBA)) return false;
  unsigned at=4;
  if(p[at]=='-'||p[at]==' ') ++at;
  else if(s[at]==0xE2 && s[at+1]==0x80 && (s[at+2]==0x91||s[at+2]==0x93))at+=3;
  if(p[at]!='6'||p[at+1]!='1')return false;
  length=at+2;return true;
}

inline int extract_pool(const char *task,Pool &pool) {
  char clean[4096];unsigned n=0;
  for(unsigned i=0;task[i];) {
    if(n+5>=sizeof(clean))return -1;
    unsigned len=0;
    if(std::strlen(task+i)>=6 && brand(task+i,len)) {
      const char replacement[]="МК";for(unsigned j=0;j<4;++j)clean[n++]=replacement[j];i+=len;
    } else if(static_cast<unsigned char>(task[i])==0xE2 && static_cast<unsigned char>(task[i+1])==0x88 && static_cast<unsigned char>(task[i+2])==0x92) { clean[n++]='-';i+=3; }
    else if(static_cast<unsigned char>(task[i])>=128) {
      // Keep Unicode word boundaries without a locale or dynamic regex.
      unsigned c=static_cast<unsigned char>(task[i]),length=0,point=0;
      if((c&0xE0)==0xC0) {length=2;point=c&31;}
      else if((c&0xF0)==0xE0) {length=3;point=c&15;}
      else if((c&0xF8)==0xF0) {length=4;point=c&7;}
      else return -4;
      for(unsigned k=1;k<length;++k) {
        unsigned next=static_cast<unsigned char>(task[i+k]);if(!next||(next&0xC0)!=0x80)return -4;
        point=(point<<6)|(next&63);
      }
      bool letter=(point>=0x400&&point<=0x52F)||(point>=0x370&&point<=0x3FF)||
        (point>=0xC0&&point<=0x2AF&&point!=0xD7&&point!=0xF7);
      clean[n++]=letter?'W':' ';i+=length;
    } else clean[n++]=task[i++];
  }
  clean[n]=0;pool.count=3;std::strcpy(pool.values[0],"0");std::strcpy(pool.values[1],"1");std::strcpy(pool.values[2],"-1");
  for(unsigned i=0;i<n;) {
    if(i && word(static_cast<unsigned char>(clean[i-1]))) { ++i;continue; }
    unsigned start=i,j=i;if(clean[j]=='-'||clean[j]=='+')++j;
    unsigned integerStart=j;while(j<n&&digit(clean[j]))++j;unsigned integerEnd=j;
    bool hasDigits=j>integerStart;
    if(j<n&&clean[j]=='.') { ++j;unsigned f=j;while(j<n&&digit(clean[j]))++j;hasDigits=hasDigits||j>f; }
    if(!hasDigits) { ++i;continue; }
    if(j<n&&word(static_cast<unsigned char>(clean[j]))) {
      if(integerEnd>integerStart&&clean[integerEnd]=='.')j=integerEnd;
      else { ++i;continue; }
    }
    char value[NumberMax];if(canonical(clean+start,j-start,value))return -2;
    bool exists=false;for(unsigned k=0;k<pool.count;++k)if(!std::strcmp(pool.values[k],value))exists=true;
    if(!exists) { if(pool.count==PoolMax)return -3;std::strcpy(pool.values[pool.count++],value); }
    i=j;
  }
  return 0;
}

inline int literal(const char *number,std::uint8_t *out,unsigned &used,unsigned capacity) {
  bool negative=number[0]=='-';const char *p=number+(negative?1:0);unsigned n=std::strlen(p);
  if(!n||n>18||used+2+n+(negative?1:0)>capacity)return -1;
  out[used++]=0x0E;out[used++]=0x0D;
  for(unsigned i=0;i<n;++i) {
    if(p[i]=='.')out[used++]=0x0A;
    else if(digit(p[i]))out[used++]=p[i]-'0';
    else return -1;
  }
  if(negative)out[used++]=0x0B;
  return 0;
}

inline int assemble(const std::uint8_t *body,unsigned size,const Pool &pool,bool macros,std::uint8_t *out,unsigned &used,Workspace &work) {
  if(size==0||size>BodyMax)return -1;used=0;work.count=0;
  if(!macros) { if(size>ProgramMax)return -2;std::memcpy(out,body,size);used=size;return 0; }
  for(auto &v:work.labels)v=0xFFFF;
  for(unsigned at=0;at<size;) {
    unsigned op=body[at++];
    if(op!=0xFF) { if(used==ProgramMax)return -2;out[used++]=op;continue; }
    if(at==size)return -3;unsigned directive=body[at++];
    if(directive==0) { if(used==ProgramMax)return -2;out[used++]=0xFF;continue; }
    if(at==size)return -3;unsigned argument=body[at++];
    if(directive==1) { if(argument>=pool.count||literal(pool.values[argument],out,used,ProgramMax))return -4; }
    else if(directive==2) { if(work.labels[argument]!=0xFFFF)return -5;work.labels[argument]=used; }
    else if(directive==3) {
      if(used==ProgramMax||work.count==ProgramMax)return -2;
      work.relocations[work.count++]={static_cast<std::uint8_t>(used),static_cast<std::uint8_t>(argument)};out[used++]=0;
    } else return -6;
  }
  for(unsigned i=0;i<work.count;++i) {
    auto r=work.relocations[i];unsigned address=work.labels[r.label];
    if(address>=ProgramMax)return -7;
    out[r.position]=static_cast<std::uint8_t>((address/10)*16+address%10);
  }
  return used?0:-8;
}

inline int patch(std::uint8_t *body,unsigned &size,const std::uint8_t *values,unsigned count) {
  if(count<2)return -1;unsigned at=unsigned(values[0])*256+values[1],result=at+count-2;
  if(at>size||result==0||result>BodyMax)return -2;
  std::memmove(body+at,values+2,count-2);size=result;return 0;
}

inline const char *spaces(const char *p) { while(*p&&std::isspace(static_cast<unsigned char>(*p)))++p;return p; }
inline bool tail(const char *p,const char *suffix) {
  unsigned n=std::strlen(suffix);return !std::strncmp(p,suffix,n)&&!*spaces(p+n);
}
inline bool closing_run(const char *p,const char *closing) {
  unsigned n=std::strlen(closing);return !std::strncmp(p,closing,n)&&tail(spaces(p+n),"<run/>");
}
inline int read_body(const char *p,const char *closing,std::uint8_t *out,unsigned &size) {
  size=0;
  while(true) {
    p=spaces(p);if(closing_run(p,closing))return size?0:-1;
    int a=hex(p[0]),b=p[0]?hex(p[1]):-1;if(a<0||b<0||size==BodyMax)return -2;
    out[size++]=a*16+b;p+=2;
    if(*p&&!std::isspace(static_cast<unsigned char>(*p))&&*p!='<')return -2;
  }
}

inline int parse_reply(const char *reply,State &state,bool macros,Action &action,unsigned &test,std::uint8_t *program,unsigned &programSize,Workspace &work) {
  const char *p=spaces(reply);std::uint8_t candidate[BodyMax];unsigned n=0;
  if(!std::strncmp(p,"<write>",7)) {
    if(read_body(p+7,"</write>",candidate,n))return -1;
    action=Action::Write;
  } else if(!std::strncmp(p,"<patch>",7)) {
    std::uint8_t values[BodyMax];unsigned count=0;
    if(read_body(p+7,"</patch>",values,count))return -1;
    std::memcpy(candidate,state.body,state.size);n=state.size;
    if(patch(candidate,n,values,count))return -2;
    action=Action::Patch;
  } else if(tail(p,"<trace/>")) { action=Action::Trace;return 0; }
  else if(tail(p,"<done/>")) { action=Action::Done;return 0; }
  else if(!std::strncmp(p,"<run>",5)&&hex(p[5])>=0&&hex(p[6])>=0&&tail(p+7,"</run>")) {
    action=Action::Run;test=hex(p[5])*16+hex(p[6]);return 0;
  } else return -3;
  if(assemble(candidate,n,state.pool,macros,program,programSize,work))return -4;
  std::memcpy(state.body,candidate,n);state.size=n;return 0;
}
}

