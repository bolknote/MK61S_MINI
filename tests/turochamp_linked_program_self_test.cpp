// Real, unmodified chess sources. Both routes use precompiled, validated LBV2;
// this is NOT a comparison with recompiling every module on the host.
#include "vm_program_builder.hpp"
#include "../tools/turochamp/layout.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <iterator>
#if MK61_MATH_BACKEND == MK61_MATH_BACKEND_CORE
#include "mk61emu_core.h"
#endif
using namespace language_vm;
namespace {
struct Context {
  Value variables[26]={},array[385]={},stack[MAX_STACK]={};
  double refs[20]={};uint32_t polls=0;bool single=false;
  std::vector<uint32_t> order;
  uint64_t events=14695981039346656037ULL;
  linked::Host host() {
    return {this,[](void* raw,Language language,Bindings& b){auto& c=*(Context*)raw;if(language!=Language::BASIC)return false;b={c.variables,c.array,385,c.stack,MAX_STACK};return true;},
      [](void* raw,uint32_t symbol,uint16_t,Language){((Context*)raw)->order.push_back(symbol);return true;},
      [](void* raw,uint32_t,uint32_t& next){auto& c=*(Context*)raw;const double ref=c.refs[18];
        if(!mk_math::is_finite(ref) || ref<0 || ref>UINT32_MAX || mk_math::floor(ref)!=ref)return false;
        next=c.single?0:uint32_t(ref);return true;}};
  }
  Services services() {
    Services s={};s.context=this;
    s.service=[](void* raw){++((Context*)raw)->polls;return true;};
    s.math=[](void*,Function f,double a,double b) {
      switch(f){case Function::SIN:return mk_math::sin(a);case Function::COS:return mk_math::cos(a);
        case Function::TAN:return mk_math::tan(a);case Function::ASIN:return mk_math::asin(a);
        case Function::ACOS:return mk_math::acos(a);case Function::ATAN:return mk_math::atan(a);
        case Function::LN:return mk_math::ln(a);case Function::LOG10:return mk_math::log10(a);
        case Function::EXP:return mk_math::exp(a);case Function::SQRT:return mk_math::sqrt(a);
        default:return mk_math::pow(a,b);}
    };
    s.value=[](void*,Function f){return f==Function::COLS?26.:f==Function::ROWS?9.:f==Function::SIZE?768.:0.;};
    s.reference=[](void* raw,bool write,uint8_t ref,double& value){auto& c=*(Context*)raw;if(ref>=20)return false;if(write)c.refs[ref]=value;else value=c.refs[ref];return true;};
    s.event=[](void* raw,Event e,const char* text,uint16_t length,double& value){auto& c=*(Context*)raw;
      c.events=(c.events^unsigned(e))*1099511628211ULL;c.events=(c.events^length)*1099511628211ULL;
      c.events=(c.events^mk_math::binary64_bits(value))*1099511628211ULL;
      // Several non-text events use length as a command/format parameter.
      if(text)for(unsigned i=0;i<length;++i)c.events=(c.events^uint8_t(text[i]))*1099511628211ULL;
      return e!=Event::READ_INPUT && e!=Event::READ_KEY && e!=Event::WAIT;};
    return s;
  }
};
View plain_view(const linked::Program& p,const linked::Member& m) {
  const auto& c=m.validated;
  return {p.input.bytes+m.offset,c.size,c.code,c.lines,c.source_size,c.stack,c.language,false,
      bool(c.flags&2),c.end,nullptr,c.wide};
}
uint32_t call(const linked::Program& p,Context& c,unsigned entry,bool fused) {
  c.refs[18]=entry;
  if(fused) {
    linked::Session session{};if(!linked::start(p,session,entry))throw std::runtime_error("linked start");
    const auto r=linked::execute(p,session,c.host(),c.services(),100000000);
    if(r.status!=linked::Status::DONE)throw std::runtime_error(std::string("linked execution ")+error_name(r.run.error)+" symbol="+std::to_string(r.symbol));
    return r.members;
  }
  Continuation control{};Bindings bank{};auto host=c.host();host.bind(host.context,Language::BASIC,bank);
  uint32_t count=0,id=entry;
  while(id && count<100000) {
    const linked::Member* m=nullptr;
    for(unsigned i=0;i<p.count;++i)if(p.members[i].symbol==id)m=p.members+i;
    if(!m)throw std::runtime_error("missing reference member");
    host.enter(host.context,id,m->source_id,Language::BASIC);auto v=plain_view(p,*m);
    auto r=run(v,control,bank,c.services(),100000000);
    if(r.error!=Error::NONE)throw std::runtime_error(std::string("reference ")+error_name(r.error));
    ++count;if(!host.next(host.context,id,id))throw std::runtime_error("reference selector");
  }
  if(id)throw std::runtime_error("reference loop limit");return count;
}
Context search(const linked::Program& p,bool fused,double& elapsed,uint32_t& launches) {
  Context c;c.single=true;call(p,c,tc::M_INIT,fused);c.single=false;
  c.array[tc::LEVEL]=2;c.array[tc::BOOK_ENABLED]=0;
  c.order.clear();c.polls=0;
  const auto begin=std::chrono::steady_clock::now();launches=0;
  for(int part:{tc::M_STATUS,tc::M_SEARCH}) {
    c.array[tc::SP]=1;c.array[tc::RETURNS]=0;c.array[tc::PHASE]=0;
    launches+=call(p,c,unsigned(part),fused);
  }
  elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
  if(c.array[tc::NODES]!=Value(420) || c.array[tc::BEST]!=Value(5795) || c.array[tc::ROOTVAL]!=Value(54))
    throw std::runtime_error("golden search differs");
  return c;
}
}
int main(int argc,char** argv) {
  try {
    if(argc!=2)return 2;
#if MK61_MATH_BACKEND == MK61_MATH_BACKEND_CORE
    core_61::enable();
#endif
    std::vector<vm_program_builder::Member> source;std::map<std::string,std::pair<uint16_t,vm_program_builder::Bytes>> files;
    for(const auto& m:tc::MODULES) {
      auto found=files.find(m.name);
      if(found==files.end()) {
        std::ifstream file(std::string(argv[1])+"/"+m.name+".tbi",std::ios::binary);
        if(!file)throw std::runtime_error("missing source");
        std::string text(std::istreambuf_iterator<char>(file),{});
        found=files.emplace(m.name,std::make_pair(uint16_t(files.size()+1),vm_program_builder::compile(Language::BASIC,text))).first;
      }
      source.push_back({uint32_t(m.id),found->second.first,found->second.second});
    }
    auto bytes=vm_program_builder::package(source,tc::M_INIT);
    linked::Input in{};in.bytes=bytes.data();in.size=uint32_t(bytes.size());
    std::vector<linked::Member> members(source.size());linked::Program program;vm_program_builder::Disk disk;
    if(linked::inspect(in,members.data(),uint16_t(members.size()),program,disk.io())!=Error::NONE)throw std::runtime_error("bad chess package");
    double times[3];uint32_t launches[3];auto a=search(program,false,times[0],launches[0]);
    auto b=search(program,true,times[1],launches[1]);auto c=search(program,false,times[2],launches[2]);
    for(unsigned i=0;i<26;++i)if(a.variables[i].representation()!=b.variables[i].representation() || a.variables[i].representation()!=c.variables[i].representation())throw std::runtime_error("variable mismatch");
    for(unsigned i=0;i<385;++i)if(a.array[i].representation()!=b.array[i].representation() || a.array[i].representation()!=c.array[i].representation())throw std::runtime_error("array mismatch");
    if(memcmp(a.refs,b.refs,sizeof(a.refs)) || memcmp(a.refs,c.refs,sizeof(a.refs)) ||
       a.order!=b.order || a.order!=c.order || a.events!=b.events || a.events!=c.events ||
       a.polls!=b.polls || a.polls!=c.polls || launches[0]!=launches[1] || launches[0]!=launches[2])throw std::runtime_error("route/event/reference/poll mismatch");
    std::cout<<"linked chess backend="<<MK61_MATH_BACKEND<<" source_files="<<files.size()<<" symbols="<<members.size()
        <<" package="<<bytes.size()<<" directory="<<linked::HEADER_BYTES+members.size()*linked::ENTRY_BYTES
        <<" session="<<sizeof(linked::Session)<<" catalog="<<members.size()*sizeof(linked::Member)
        <<" vm_runs="<<launches[1]<<" polls="<<b.polls<<" e2e3/54/420, exact banks/tags/events/routes PASS\n";
    std::cout<<"host-only A/B/A seconds="<<times[0]<<'/'<<times[1]<<'/'<<times[2]<<"; no device speed claim\n";
  } catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
