#include "language_linked_program.hpp"
#include <limits.h>

namespace language_vm { namespace linked {
namespace {
uint32_t epoch(const Input& in) {return in.epoch?in.epoch(in.epoch_context):0;}
bool read(const Input& in,uint32_t at,void* out,uint16_t n) {
  if(at>in.size || n>in.size-at || (!out && n))return false;
  if(in.bytes){if(n)memcpy(out,in.bytes+at,n);return true;}
  return in.paged.read && in.paged.size==in.size && in.paged.read(in.paged.context,at,(uint8_t*)out,n);
}
struct Slice {
  const Input& input;uint32_t offset,size,stamp;
  static bool read(void* raw,uint32_t at,uint8_t* out,uint16_t n) {
    const auto& s=*(Slice*)raw;
    return epoch(s.input)==s.stamp && at<=s.size && n<=s.size-at &&
        linked::read(s.input,s.offset+at,out,n) && epoch(s.input)==s.stamp;
  }
  flash::Input paged() {return {this,read,size};}
};
bool checksum_input(const Input& in,uint32_t at,uint32_t& crc,flash::IO scratch) {
  const uint32_t stamp=epoch(in);
  crc=~uint32_t(0);uint8_t bytes[128];
  while(at<in.size) {
    const auto n=uint16_t(in.size-at<sizeof(bytes)?in.size-at:sizeof(bytes));
    if(!read(in,at,bytes,n))return false;
    for(uint16_t i=0;i<n;++i){crc^=bytes[i];for(unsigned b=0;b<8;++b)crc=(crc>>1)^(0xEDB88320U&(0U-(crc&1U)));}
    at+=n;if(!scratch.poll() || epoch(in)!=stamp)return false;
  }
  crc=~crc;return true;
}
int find(const Program& p,uint32_t symbol) {
  unsigned low=0,high=p.count;
  while(low<high){const unsigned middle=(low+high)/2;if(p.members[middle].symbol<symbol)low=middle+1;else high=middle;}
  return low<p.count && p.members[low].symbol==symbol?int(low):-1;
}
ValidatedImage certificate(const View& v,uint8_t flags) {
  return {VALIDATED_MAGIC,v.size,v.code,v.source_size,v.end,v.lines,v.stack,flags,v.language,v.wide};
}
View view(const Member& m,const Input& in,const flash::Reader* reader) {
  const auto& c=m.validated;
  return {in.bytes?in.bytes+m.offset:nullptr,c.size,c.code,c.lines,c.source_size,c.stack,c.language,
      false,(c.flags&2)!=0,c.end,reader,c.wide};
}
struct MapContext {View& view;const Program& program;};
bool lookup(void* raw,uint32_t key,bool number,uint32_t* out) {
  auto& context=*(MapContext*)raw;auto& v=context.view;
  // VM completion also asks for a source line after a callback stopped RUN.
  // An invalidated raw image may already have been freed by that callback.
  if(!current(context.program)){*out=number?v.missing():0;if(v.reader)v.reader->fail();return false;}
  const unsigned stride=v.wide?8:v.language==Language::BASIC?4:6;
  auto address=[&](unsigned i){auto p=v.at(HEADER_SIZE+uint32_t(i)*stride+stride-(v.wide?4:2));return v.wide?flash::dword(p):uint32_t(flash::word(p));};
  auto label=[&](unsigned i){auto p=v.at(HEADER_SIZE+uint32_t(i)*stride);return v.wide || v.language==Language::FOCAL?flash::dword(p):uint32_t(flash::word(p));};
  unsigned low=0,high=v.lines;
  while(low<high){unsigned middle=(low+high)/2;uint32_t at=number?label(middle):address(middle);if(at<key || (!number && at==key))low=middle+1;else high=middle;}
  *out=number?(low<v.lines && label(low)==key?address(low):v.missing()):(low?label(low-1):0);
  return v.good();
}
struct Bridge {
  const Program& program;const Services& services;bool stale=false;
  bool valid(){if(!current(program))stale=true;return !stale;}
  static bool poll(void* raw) {
    auto& b=*(Bridge*)raw;
    if(!b.valid())return false;
    const bool ok=!b.services.service || b.services.service(b.services.context);
    return b.valid() && ok;
  }
  static double math(void* p,Function f,double a,double c){auto& b=*(Bridge*)p;if(!b.valid())return __builtin_nan("");double v=b.services.math?b.services.math(b.services.context,f,a,c):__builtin_nan("");return b.valid()?v:__builtin_nan("");}
  static double random(void* p){auto& b=*(Bridge*)p;if(!b.valid())return __builtin_nan("");double v=b.services.random?b.services.random(b.services.context):0;return b.valid()?v:__builtin_nan("");}
  static double value(void* p,Function f){auto& b=*(Bridge*)p;if(!b.valid())return __builtin_nan("");double v=b.services.value?b.services.value(b.services.context,f):0;return b.valid()?v:__builtin_nan("");}
  static bool reference(void* p,bool w,uint8_t r,double& v){auto& b=*(Bridge*)p;return b.valid() && b.services.reference && b.services.reference(b.services.context,w,r,v) && b.valid();}
  static bool event(void* p,Event e,const char* s,uint16_t n,double& v){auto& b=*(Bridge*)p;return b.valid() && (!b.services.event || b.services.event(b.services.context,e,s,n,v)) && b.valid();}
};
Result result(const Session& s,Status status,RunResult r={},uint16_t source=0xFFFF) {
  return {status,r,s.symbol,s.steps,s.members,source};
}
}

bool current(const Program& p){return p.members && p.count && p.count<=MAX_MEMBERS && p.epoch==epoch(p.input);}
Error inspect(Input in,Member* members,uint16_t capacity,Program& out,flash::IO scratch) {
  out={};uint8_t h[HEADER_BYTES];
  const uint32_t stamp=epoch(in);
  auto read_current=[&](uint32_t at,void* bytes,uint16_t size) {
    return epoch(in)==stamp && read(in,at,bytes,size) && epoch(in)==stamp;
  };
  if(!members || in.size<HEADER_BYTES || (!in.bytes && (!in.paged.read || in.paged.size!=in.size)))return Error::INVALID_IMAGE;
  if(!read_current(0,h,sizeof(h)))return Error::IO;
  const uint16_t count=flash::word(h+6);
  if(memcmp(h,"LVP1",4) || h[4]!=VERSION || h[5] || !count || count>MAX_MEMBERS || count>capacity ||
     flash::dword(h+8)!=in.size || !flash::dword(h+12) || flash::dword(h+16)!=uint32_t(count)*ENTRY_BYTES ||
     flash::dword(h+20) || checksum(h,28)!=flash::dword(h+28))return Error::INVALID_IMAGE;
  uint32_t crc;
  if(!checksum_input(in,HEADER_BYTES,crc,scratch))return Error::IO;
  if(crc!=flash::dword(h+24))return Error::INVALID_IMAGE;
  uint32_t previous=0,next=HEADER_BYTES+uint32_t(count)*ENTRY_BYTES;
  if(next>in.size)return Error::INVALID_IMAGE;
  for(uint16_t i=0;i<count;++i) {
    uint8_t e[ENTRY_BYTES],header[HEADER_SIZE];
    if(!read_current(HEADER_BYTES+uint32_t(i)*ENTRY_BYTES,e,sizeof(e)))return Error::IO;
    const uint32_t symbol=flash::dword(e),offset=flash::dword(e+4),size=flash::dword(e+8),source=flash::dword(e+12);
    if(!symbol || symbol<=previous || size<HEADER_SIZE || offset>in.size || size>in.size-offset || source>0xFFFF)
      return Error::INVALID_IMAGE;
    if(offset!=next) {
      unsigned alias=0;
      while(alias<i && (members[alias].offset!=offset || members[alias].validated.size!=size || members[alias].source_id!=source))++alias;
      if(alias==i)return Error::INVALID_IMAGE;
      members[i]=members[alias];members[i].symbol=symbol;previous=symbol;continue;
    }
    if(!read_current(offset,header,sizeof(header)))return Error::IO;
    // A linked image is source-independent. Recipes referring to separately
    // mutable source files cannot be silently treated as owned resources.
    if((header[7]&1) || ((header[7]&RESOURCE_FLAG) && !(header[7]&OWNED_RESOURCE_FLAG)))return Error::INVALID_IMAGE;
    auto supported=[&](const View& v) {
      unsigned operations=0;
      for(uint32_t pc=v.code;pc<v.end;) {
        if(v.byte(pc)==uint8_t(Op::GRAPH_BEGIN))return Error::GRAPHICS_UNAVAILABLE;
        const uint32_t following=instruction_end(v,pc);
        if(!following)return v.good()?Error::INVALID_IMAGE:Error::IO;
        pc=following;
        if((++operations&31U)==0) {
          if(!scratch.poll())return Error::STOPPED;
          if(epoch(in)!=stamp)return Error::IO;
        }
      }
      return v.good()?Error::NONE:Error::IO;
    };
    View v={};Error error;
    if(!memcmp(header,"LBV1",4)) {
#if defined(MK61_BUILD_LANGUAGE_VM_MODULE) || defined(MK61_BUILD_LANGUAGE_INPUT_MODULE)
      return Error::INVALID_IMAGE;
#else
      if(!in.bytes || size>MAX_MODULE)return Error::INVALID_IMAGE;
      error=language_vm::inspect(in.bytes+offset,uint16_t(size),v);
      if(error==Error::NONE)error=supported(v);
#endif
    } else {
      Slice slice{in,offset,size,stamp};flash::Reader reader(slice.paged());
      // Validation scratch is not a line-map provider for every member.
      auto temporary=scratch;temporary.lookup=nullptr;
      error=inspect_flash(reader,temporary,v);
      if(error==Error::NONE)error=supported(v);
    }
    if(error!=Error::NONE)return error;
    members[i]={symbol,offset,uint16_t(source),certificate(v,header[7])};
    previous=symbol;next=offset+size;
    if(!scratch.poll())return Error::STOPPED;
    if(epoch(in)!=stamp)return Error::IO;
  }
  if(next!=in.size)return Error::INVALID_IMAGE;
  if(epoch(in)!=stamp)return Error::IO;
  Program candidate{in,members,count,flash::dword(h+12),stamp,flash::dword(h+28)};
  if(find(candidate,candidate.entry)<0)return Error::INVALID_IMAGE;
  out=candidate;return Error::NONE;
}
bool start(const Program& p,Session& s,uint32_t entry) {
  s.phase=Phase::EMPTY;
  if(!current(p))return false;
  if(!entry)entry=p.entry;
  const int index=find(p,entry);if(index<0)return false;
  s.identity=p.identity;s.epoch=p.epoch;s.symbol=entry;s.steps=s.members=0;
  s.index=uint16_t(index);s.phase=Phase::ENTER;return true;
}
Result execute_with(const Program& p,Session& s,const Host& host,const Services& services,Kernel kernel,uint32_t budget,const Value* input) {
  if(!current(p) || s.identity!=p.identity || s.epoch!=p.epoch) {
    s.phase=Phase::FAILED;return result(s,Status::INVALIDATED);
  }
  if(!kernel || !host.bind || !host.next || (host.borrow && !host.release) || s.phase==Phase::EMPTY || s.phase==Phase::FAILED || unsigned(s.phase)>unsigned(Phase::FAILED))
    return result(s,Status::ERROR,{Error::INVALID_IMAGE,0,0,0});
  if(s.phase==Phase::DONE)return result(s,Status::DONE);
  uint32_t used=0;
  Bridge bridge{p,services};
  Services callbacks={&bridge,Bridge::poll,services.math?Bridge::math:nullptr,services.random?Bridge::random:nullptr,
      services.value?Bridge::value:nullptr,services.reference?Bridge::reference:nullptr,services.event?Bridge::event:nullptr,
      true,services.isolate_print};
  for(;;) {
    if(s.index>=p.count || p.members[s.index].symbol!=s.symbol) {
      const int index=find(p,s.symbol);
      if(index<0)return result(s,Status::UNRESOLVED);
      s.index=uint16_t(index);
    }
    const auto& m=p.members[s.index];Bindings data={};
    if(!host.bind(host.context,m.validated.language,data)) {
      s.phase=Phase::FAILED;return result(s,Status::ERROR,{Error::VARIABLE,0,0,0},m.source_id);
    }
    if(!data.variables || !data.stack || data.stack_capacity>MAX_STACK || data.stack_capacity<m.validated.stack ||
       data.array_count>(m.validated.language==Language::BASIC?385:64) || (data.array_count && !data.array)) {
      s.phase=Phase::FAILED;return result(s,Status::ERROR,{Error::INVALID_IMAGE,0,0,0},m.source_id);
    }
    if(s.phase==Phase::AWAIT_INPUT) {
      if(!input)return result(s,Status::AWAIT_INPUT,{Error::YIELDED,s.control.pc,0,0},m.source_id);
      if(!data.stack || s.control.sp>=data.stack_capacity) {
        s.phase=Phase::FAILED;return result(s,Status::ERROR,{Error::STACK,s.control.pc,0,0},m.source_id);
      }
      data.stack[s.control.sp++]=*input;input=nullptr;s.phase=Phase::RUN;
    } else if(input)return result(s,Status::ERROR,{Error::INVALID_IMAGE,0,0,0},m.source_id);
    const bool resume=s.phase==Phase::RUN;
    if(!resume && host.enter && !host.enter(host.context,s.symbol,m.source_id,m.validated.language)) {
      s.phase=Phase::FAILED;return result(s,Status::ERROR,{Error::IO,0,0,0},m.source_id);
    }
    if(!bridge.valid()){s.phase=Phase::FAILED;return result(s,Status::INVALIDATED,{},m.source_id);}
    struct Loan {
      const Host& host;const uint8_t* image=nullptr;
      ~Loan(){if(image && host.release)host.release(host.context,image);}
    } loan{host};
    if(host.borrow && !host.borrow(host.context,m,loan.image)) {
      s.phase=Phase::FAILED;return result(s,Status::ERROR,{Error::IO,0,0,0},m.source_id);
    }
    if(!bridge.valid()){s.phase=Phase::FAILED;return result(s,Status::INVALIDATED,{},m.source_id);}
    Slice slice{p.input,m.offset,m.validated.size,p.epoch};flash::Reader reader(slice.paged());
    View v=view(m,p.input,p.input.bytes?nullptr:&reader);
    if(loan.image){v.bytes=loan.image;v.reader=nullptr;}
    MapContext map{v,p};v.lookup_context=&map;v.lookup=lookup;
    const auto r=kernel(v,s.control,data,callbacks,budget?budget-used:0,resume);
    used+=r.steps;
    if(s.steps>UINT32_MAX-r.steps){s.phase=Phase::FAILED;return result(s,Status::ERROR,{Error::LIMIT,r.pc,r.line,r.steps},m.source_id);}
    s.steps+=r.steps;
    if(!bridge.valid()){s.phase=Phase::FAILED;return result(s,Status::INVALIDATED,r,m.source_id);}
    if(r.error==Error::YIELDED){s.phase=Phase::AWAIT_INPUT;return result(s,Status::AWAIT_INPUT,r,m.source_id);}
    if(r.error==Error::LIMIT){s.phase=Phase::RUN;return result(s,Status::BUDGET,r,m.source_id);}
    if(r.error!=Error::NONE){s.phase=Phase::FAILED;return result(s,Status::ERROR,r,m.source_id);}
    ++s.members;uint32_t next=0;
    if(!host.next(host.context,s.symbol,next)) {
      s.phase=Phase::FAILED;return result(s,Status::ERROR,{Error::IO,r.pc,r.line,r.steps},m.source_id);
    }
    if(!bridge.valid()){s.phase=Phase::FAILED;return result(s,Status::INVALIDATED,r,m.source_id);}
    if(!next){s.phase=Phase::DONE;return result(s,Status::DONE,r,m.source_id);}
    s.symbol=next;s.index=UINT16_MAX;s.phase=Phase::ENTER;
    if(budget && used>=budget)return result(s,Status::BUDGET,r,m.source_id);
  }
}
}}
