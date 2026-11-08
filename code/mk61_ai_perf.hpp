#ifndef MK61_AI_PERF_HPP
#define MK61_AI_PERF_HPP
#include <cstring>
namespace mk61ai {
struct PerfConfig {
  unsigned kernel=0,arithmetic=3,cores=1,freeze=0,filter=0,mhz=125;
  unsigned prefill=8,decode=4,repeat=1,stress_ms=0,control=0,constrained=0;
  unsigned prefetch=0,version=1;
};
// Strict, bounded, reviewable SD diagnostic configuration. All fields must be
// present once. An invalid file cannot silently enable a clock experiment.
inline bool parse_perf_config(const char *text,unsigned size,PerfConfig& out) {
  if(!text || size<9 || size>512) return false;
  const bool v2=!std::memcmp(text,"AIPERF2\n",8);
  if(!v2 && std::memcmp(text,"AIPERF1\n",8)) return false;
  static const char* const keys[]={"kernel","arithmetic","cores","freeze","filter","mhz",
      "prefill","decode","repeat","stress_ms","control","constrained","prefetch"};
  const unsigned fields=v2?13:12;
  unsigned values[13]{},seen=0,at=8;
  while(at<size) {
    unsigned begin=at;while(at<size && text[at]!='=' && text[at]!='\n') ++at;
    if(at==size || text[at]!='=') return false;
    unsigned key=fields;
    for(unsigned i=0;i<fields;++i)
      if(std::strlen(keys[i])==at-begin && !std::memcmp(text+begin,keys[i],at-begin)) key=i;
    if(key==fields || (seen&(1U<<key))) return false;
    ++at;begin=at;unsigned value=0;
    while(at<size && text[at]>='0' && text[at]<='9') {
      value=value*10+unsigned(text[at++]-'0');if(value>300000) return false;
    }
    if(at==begin || (at<size && text[at]!='\n')) return false;
    if(at<size) ++at;
    values[key]=value;seen|=1U<<key;
  }
  if(seen!=((1U<<fields)-1) || values[0]>2 || values[1]>3 || values[2]<1 || values[2]>3 ||
     values[3]>1 || values[4]>1 || (values[5]!=125 && values[5]!=200 && values[5]!=250 && values[5]!=270 && values[5]!=300) ||
     values[6]<1 || values[6]>16 || values[7]<1 || values[7]>8 || values[6]+values[7]>24 ||
     values[8]<1 || values[8]>4 || values[10]>2 || (values[10]==2 && (!v2 || values[2]<2)) || values[11]>1 || values[12]>1 ||
     (!values[0] && (values[2]!=1 || values[4] || values[12])) || (values[4] && !values[11])) return false;
  // control=2 uses archived tokens/checksums in PERF.REF and runs only the
  // requested two- or three-core candidate; it never executes a control pass.
  if(values[2]==3 && (!v2 || (values[1]!=3 && values[1]!=1) || !values[10] || values[9])) return false;
  out={values[0],values[1],values[2],values[3],values[4],values[5],
       values[6],values[7],values[8],values[9],values[10],values[11],values[12],v2?2U:1U};
  return true;
}
}
#endif
