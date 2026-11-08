#include "mk61_ai_agent.hpp"
#include "mk61_ai_worker_fixture.hpp"
#include "mk61emu_core.h"
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <map>
#include <sstream>
#include <string>
#include <vector>
using namespace mk61ai;
namespace {
struct Disk {
  std::map<std::string,std::vector<std::uint8_t>> files;
  Store store() { return {this,
    [](void *p,const char *path,void *out,unsigned cap,unsigned &n) {
      auto &files=static_cast<Disk*>(p)->files;auto at=files.find(path);
      if(at==files.end()||at->second.size()>cap)return false;
      n=unsigned(at->second.size());std::memcpy(out,at->second.data(),n);return true;
    },
    [](void *p,const char *path,const void *raw,unsigned n) {
      const auto b=static_cast<const std::uint8_t*>(raw);
      static_cast<Disk*>(p)->files[path]={b,b+n};return true;
    },
    [](void *p,const char *path){return static_cast<Disk*>(p)->files.count(path)!=0;}};
  }
};
bool read(void *p,std::uint32_t at,void *out,unsigned n) {
  auto &data=*static_cast<std::vector<std::uint8_t>*>(p);
  if(at>data.size()||n>data.size()-at)return false;
  std::memcpy(out,data.data()+at,n);return true;
}
bool write(void *p,std::uint32_t at,const void *raw,unsigned n) {
  auto &data=*static_cast<std::vector<std::uint8_t>*>(p);
  if(at>data.size()||n>data.size()-at)return false;
  std::memcpy(data.data()+at,raw,n);return true;
}
std::string hex(const std::string &text) {
  std::string out;int half=-1;
  for(char c:text){
    if(c==' ')continue;
    const int value=c<='9'?c-'0':c<='F'?c-'A'+10:c-'a'+10;
    assert(value>=0&&value<16);
    if(half<0)half=value;else{out.push_back(char(half*16+value));half=-1;}
  }
  assert(half<0);return out;
}
struct Observed {
  Model *model;
  std::vector<unsigned> tokens;
  Inference inference() {
    auto result=local_inference(*model);
    result.context=this;
    result.configuration=[](void *p)->const ModelConfig&{return static_cast<Observed*>(p)->model->config();};
    result.cursor=[](void *p){return static_cast<Observed*>(p)->model->position();};
    result.seek=[](void *p,unsigned n){return static_cast<Observed*>(p)->model->rewind(n);};
    result.encode_text=[](void *p,const char *s,std::uint16_t *ids,unsigned cap,unsigned &n,bool bos){return static_cast<Observed*>(p)->model->encode(s,ids,cap,n,bos);};
    result.decode_token=[](void *p,std::uint16_t token,char *s,unsigned cap,unsigned &n){return static_cast<Observed*>(p)->model->decode(token,s,cap,n);};
    result.step=[](void *p,std::uint16_t token,bool output,std::uint16_t &best,
      bool(*service)(void*),void *raw,Arithmetic arithmetic,bool(*allowed)(void*,std::uint16_t),void *policy){
      auto &o=*static_cast<Observed*>(p);
      const auto status=o.model->forward(token,output,best,service,raw,arithmetic,nullptr,allowed,policy);
      if(status==ModelStatus::OK&&output)o.tokens.push_back(best);return status;
    };
    return result;
  }
};
}
int main(int argc,char **argv) {
  assert(argc==3);
  std::ifstream package_file(argv[1],std::ios::binary),fixture(argv[2]);assert(package_file&&fixture);
  std::vector<std::uint8_t> package((std::istreambuf_iterator<char>(package_file)),{}),cache;
  Model model;assert(model.open({&package,unsigned(package.size()),read,nullptr})==ModelStatus::OK);
  assert(model.config().vocab==8224&&model.config().context==1024);
  ComputeExecution execution{};execution.filter_head=true;execution.kernel=LinearKernel::SRAM;
  TestAiWorker worker;
  execution.context=&worker;
  execution.submit=[](void *p,void(*fn)(void*),void *job){return static_cast<TestAiWorker*>(p)->submit(fn,job);};
  execution.join=[](void *p){static_cast<TestAiWorker*>(p)->join();};
  execution.tile_rows=28;model.execution(execution);
  cache.resize(model.cache_bytes());std::vector<std::uint64_t> workspace((model.workspace_bytes()+7)/8);
  assert(model.bind(workspace.data(),workspace.size()*8,{&cache,unsigned(cache.size()),read,write,
    [](void *p,const block_io::ReadSpan *spans,unsigned n){
      for(unsigned i=0;i<n;++i)if(!read(p,spans[i].offset,spans[i].destination,spans[i].bytes))return false;
      return true;
    },[](void*){return true;}})==ModelStatus::OK);
  core_61::enable();core_61::set_expanded_program_mode(false);
  {
    SpecProtocol spec;char prompt[Agent::PROMPT_BYTES+1];
    assert(spec.prompt("Синус −22 градусов",0,prompt,sizeof(prompt)));
    assert(!std::strcmp(spec.constant(12),"-22")&&!std::strcmp(spec.constant(13),"22"));
    assert(!spec.prompt(".12345678901234567890123",0,prompt,sizeof(prompt)));
  }
  unsigned cases=0;std::string row;
  while(std::getline(fixture,row)) {
    if(row.empty()||row[0]=='#')continue;
    std::vector<std::string> fields;std::stringstream stream(row);std::string part;
    while(std::getline(stream,part,'\t'))fields.push_back(part);assert(fields.size()==7);
    const auto task=hex(fields[0]),expected_prompt=hex(fields[2]),body=hex(fields[3]),program=hex(fields[4]);
    const unsigned angle=unsigned(std::stoul(fields[1]));
    SpecProtocol spec;char prompt[Agent::PROMPT_BYTES+1];assert(spec.prompt(task.c_str(),angle,prompt,sizeof(prompt)));
    const std::string actual_prompt=std::string(prompt)+"<";
    if(actual_prompt!=expected_prompt){
      unsigned at=0;while(at<actual_prompt.size()&&at<expected_prompt.size()&&actual_prompt[at]==expected_prompt[at])++at;
      std::fprintf(stderr,"Prompt differs at %u: actual %.100s; expected %.100s\n",at,actual_prompt.c_str()+at,expected_prompt.c_str()+at);return 1;
    }
    assert(spec.accept(SpecProtocol::WRITE,""));
    std::string body_text=fields[3];assert(spec.accept(18,body_text.c_str())&&spec.accept(SpecProtocol::END,"<"));
    Program compiled;assert(spec.compile(compiled)&&compiled.size==program.size()&&
      !std::memcmp(compiled.bytes,program.data(),compiled.size));
    Disk disk;Session session;session.id=++cases;
    assert(set_task(session,task.c_str(),false));
    Observed observed{&model,{}};Agent agent(session,disk.store(),observed.inference());
    agent.spec_protocol(true);agent.default_angle(angle);
    if(const char *mode=std::getenv("MK61_AI_SPEC_ARITHMETIC"))agent.arithmetic(Arithmetic(std::atoi(mode)));
    agent.clock([](void*){return std::uint32_t(std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count());},nullptr);
    assert(agent.start());bool paused=false;unsigned ticks=0;
    while(agent.active()&&++ticks<2200){
      if(!paused&&agent.phase()==Agent::Phase::HEADER){agent.request_pause();agent.tick();assert(agent.paused());assert(agent.start());paused=true;}
      agent.tick();
    }
    assert(!agent.active()&&paused);
    std::vector<unsigned> expected;
    std::stringstream token_stream(fields[5]);while(std::getline(token_stream,part,','))expected.push_back(unsigned(std::stoul(part)));
    assert(agent.metrics().output_tokens==expected.size());expected.push_back(30);
    if(observed.tokens!=expected){std::fprintf(stderr,"Token mismatch, case %u: ",cases);for(auto token:observed.tokens)std::fprintf(stderr,"%u,",token);std::fprintf(stderr,"\n");return 1;}
    assert(agent.prompt_size()==std::stoul(fields[6]));
    assert(session.program.size==program.size()&&!std::memcmp(session.program.bytes,program.data(),program.size()));
    assert(agent.last_result().status!=Execution::NONE&&agent.last_result().status!=Execution::CANCELLED);
    if(cases<=3){assert(agent.last_result().status==Execution::STOPPED);if(cases==1)assert(agent.last_result().x==0.3746066);}
    std::printf("SPEC real-model case=%u input=%u output=%u commands=%u core-X=%.9g PASS\n",cases,agent.prompt_size(),agent.metrics().output_tokens,unsigned(session.program.size),agent.last_result().x);
    assert(model.compute_metrics().attention_worker_jobs>0);
    if(cases==1) {
      assert(agent.reused_prefix()==0 && agent.metrics().prefill_tokens==493);
      observed.tokens.clear();agent.reset();assert(agent.start());
      assert(agent.reused_prefix()==488);
      unsigned repeats=0;while(agent.active()&&++repeats<100)agent.tick();
      assert(!agent.active()&&observed.tokens==expected && agent.metrics().prefill_tokens==498);
      assert(agent.last_result().status==Execution::STOPPED&&agent.last_result().x==0.3746066);
      std::puts("Repeated full SPEC request:488 prompt tokens reused, identical generated tokens and core result PASS");
    }
  }
  assert(cases==8);
  std::puts("SPEC: published prompts, real neural token streams, exact compiler, core execution and header pause/resume PASS");
}
