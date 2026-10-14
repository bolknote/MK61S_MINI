// Host-only frequency probe. Counts candidates only when their bytes are
// adjacent (apart from SOURCE_POS), not just adjacent in an executed trace.
// The shipping executor reports already-consumed integer blocks separately.
#include "language_bytecode.hpp"
#include <cassert>
#include <cstdlib>
#include <fstream>
#include <map>
#include <vector>

namespace language_vm {
uint16_t trace_following(const View&,uint16_t);
namespace {
struct Instruction {uint16_t pc;Op op;};
struct Trace {
  std::vector<Instruction> previous;
  std::map<std::vector<unsigned>,uint64_t> sequences;
  std::map<unsigned,uint64_t> blocks;
  uint64_t instructions=0,runs=0,array_store_in_blocks=0;
  ~Trace() {
    const char* path=std::getenv("VM_SEQUENCE_PROFILE_FILE");
    if(!path)return;
    std::ofstream out(path);
    out<<"{\"instructions\":"<<instructions<<",\"runs\":"<<runs
       <<",\"load_array_store_already_fused\":"<<array_store_in_blocks
       <<",\"integer_blocks\":[";
    bool comma=false;
    for(const auto& row:blocks) {
      if(comma)out<<',';comma=true;out<<'['<<row.first<<','<<row.second<<']';
    }
    out<<"],\"adjacent_sequences\":[";comma=false;
    for(const auto& row:sequences) {
      if(comma)out<<',';comma=true;out<<"{\"ops\":[";
      for(unsigned n=0;n<row.first.size();++n) {if(n)out<<',';out<<row.first[n];}
      out<<"],\"count\":"<<row.second<<'}';
    }
    out<<"]}\n";
  }
};
Trace trace;
uint16_t following(const View& v,uint16_t pc) {
  pc=trace_following(v,pc);
  while(pc && pc<v.end && (Op)v.bytes[pc]==Op::SOURCE_POS)pc=trace_following(v,pc);
  return pc;
}
}
void trace_instruction(const View& v,uint16_t pc,uint32_t steps) {
  if(steps==1){trace.previous.clear();++trace.runs;}
  ++trace.instructions;
  if(!trace.previous.empty() && following(v,trace.previous.back().pc)!=pc)
    trace.previous.clear();
  trace.previous.push_back({pc,(Op)v.bytes[pc]});
  if(trace.previous.size()>4)trace.previous.erase(trace.previous.begin());
  for(unsigned n=2;n<=trace.previous.size();++n) {
    std::vector<unsigned> sequence;
    for(auto i=trace.previous.end()-n;i!=trace.previous.end();++i)sequence.push_back((unsigned)i->op);
    ++trace.sequences[sequence];
  }
}
void integer_block_applied(uint16_t first,uint8_t count) {
  assert(count>=3 && count<=5);
  ++trace.blocks[count];
  // This pair is no longer an opportunity: the current block did it already.
  if(count==5) {
    assert(trace.previous.size()>=2 && trace.previous.back().op==Op::STORE &&
           (trace.previous.end()-2)->op==Op::LOAD_ARRAY);
    auto& pair=trace.sequences[{(unsigned)Op::LOAD_ARRAY,(unsigned)Op::STORE}];
    assert(pair);--pair;++trace.array_store_in_blocks;
  }
  (void)first;
  // Do not rank sequences spanning a completed block as unoptimized work.
  trace.previous.clear();
}
}
