// Optional host-only dynamic opcode profile. Link with LANGUAGE_VM_TRACE;
// VM_TRACE_FILE names the JSON report. This never enters a firmware/APP build.
#include <cstdlib>
#include <fstream>
#include <map>
#include <vector>
#include "language_bytecode.hpp"

namespace language_vm {
namespace {
struct Module {
  uint64_t runs=0, instructions=0;
  unsigned language=0, bytes=0;
  std::map<unsigned,uint64_t> pcs;
};
struct Trace {
  std::map<unsigned,uint64_t> ops;
  std::map<std::vector<unsigned>,uint64_t> sequences;
  std::map<uint32_t,Module> modules;
  std::vector<unsigned> previous;
  std::vector<uint32_t> run_order;
  ~Trace() {
    const char* path=std::getenv("VM_TRACE_FILE");
    if(!path) return;
    std::ofstream out(path);
    out<<"{\"ops\":[";
    bool comma=false;
    for(const auto& item:ops) {
      if(comma) out<<',';
      comma=true;out<<'['<<item.first<<','<<item.second<<']';
    }
    out<<"],\"sequences\":[";comma=false;
    for(const auto& item:sequences) {
      if(comma) out<<',';
      comma=true;out<<"{\"ops\":[";
      for(unsigned i=0;i<item.first.size();++i) {if(i)out<<',';out<<item.first[i];}
      out<<"],\"count\":"<<item.second<<'}';
    }
    out<<"],\"modules\":[";comma=false;
    for(const auto& item:modules) {
      if(comma)out<<',';
      comma=true;const auto& m=item.second;
      out<<"{\"source_crc\":"<<item.first<<",\"language\":"<<m.language
         <<",\"bytes\":"<<m.bytes<<",\"runs\":"<<m.runs
         <<",\"instructions\":"<<m.instructions<<",\"pcs\":[";
      bool pc_comma=false;
      for(const auto& p:m.pcs) {if(pc_comma)out<<',';pc_comma=true;out<<'['<<p.first<<','<<p.second<<']';}
      out<<"]}";
    }
    out<<"],\"run_order\":[";
    for(unsigned i=0;i<run_order.size();++i) {if(i)out<<',';out<<run_order[i];}
    out<<"]}\n";
  }
};
Trace trace;
}
void trace_instruction(const View& v,uint16_t pc,uint32_t steps) {
  const uint8_t* b=v.bytes+16;
  const uint32_t crc=(uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);
  auto& module=trace.modules[crc];module.language=(unsigned)v.language;module.bytes=v.size;
  if(steps==1) {++module.runs;trace.previous.clear();trace.run_order.push_back(crc);}
  ++module.instructions;++module.pcs[pc];
  const unsigned op=v.bytes[pc];++trace.ops[op];
  trace.previous.push_back(op);
  if(trace.previous.size()>4)trace.previous.erase(trace.previous.begin());
  for(unsigned n=2;n<=trace.previous.size();++n)
    ++trace.sequences[{trace.previous.end()-n,trace.previous.end()}];
}
}
