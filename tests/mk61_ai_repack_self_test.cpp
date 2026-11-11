#include "mk61_ai_model.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>
using namespace mk61ai;
namespace {
struct Package {
 std::vector<std::uint8_t> bytes;
 int reads=-1,writes=-1,services=-1;unsigned written=0;
 explicit Package(const std::vector<std::uint8_t>& source):bytes(source){}
 static bool read(void* raw,std::uint32_t at,void* out,unsigned n) {
  auto& p=*static_cast<Package*>(raw);
  if(p.reads==0)return false;if(p.reads>0)--p.reads;
  if(at>p.bytes.size() || n>p.bytes.size()-at)return false;
  std::memcpy(out,p.bytes.data()+at,n);return true;
 }
 static bool write(void* raw,std::uint32_t at,const void* in,unsigned n) {
  auto& p=*static_cast<Package*>(raw);
  if(p.writes==0)return false;if(p.writes>0)--p.writes;
  if(at>p.bytes.size() || n>p.bytes.size()-at)return false;
  std::memcpy(p.bytes.data()+at,in,n);++p.written;return true;
 }
 static bool service(void* raw) {
  auto& p=*static_cast<Package*>(raw);return p.services<0 || p.services-->0;
 }
 Memory memory(bool writable=true){return {this,unsigned(bytes.size()),read,writable?write:nullptr};}
};
std::vector<std::uint8_t> file(const char* path) {
 std::ifstream f(path,std::ios::binary);assert(f);return {std::istreambuf_iterator<char>(f),{}};
}
}
int main(int argc,char** argv) {
 assert(argc==4);const auto source=file(argv[1]),expected=file(argv[2]),planes=file(argv[3]);
 for(const auto* input:{&source,&planes,&expected}) {
  Package p(*input);Model m;assert(m.open(p.memory())==ModelStatus::OK);
  assert(m.repack_lut8(Package::service,&p)==ModelStatus::OK && p.bytes==expected);
  const auto writes=p.written;assert(m.repack_lut8()==ModelStatus::OK && p.written==writes);
  Model verify;assert(verify.open(p.memory(false))==ModelStatus::OK);
 }
 Package readonly(source);Model m;assert(m.open(readonly.memory(false))==ModelStatus::OK);
 assert(m.repack_lut8()==ModelStatus::MEMORY && readonly.bytes==source);
 for(int limit:{0,3,200}) {
  Package p(source);Model model;assert(model.open(p.memory())==ModelStatus::OK);p.services=limit;
  assert(model.repack_lut8(Package::service,&p)==ModelStatus::CANCELLED);
  if(!limit)assert(!p.written && p.bytes==source);
 }
 for(bool writing:{false,true})for(int limit:{0,3,200}) {
  Package p(source);Model model;assert(model.open(p.memory())==ModelStatus::OK);
  if(writing)p.writes=limit;else p.reads=limit;
  assert(model.repack_lut8()==ModelStatus::IO);
 }
 Package p(source);Model bound;assert(bound.open(p.memory())==ModelStatus::OK);
 std::vector<std::uint64_t> workspace((bound.workspace_bytes()+7)/8);
 Package cache(std::vector<std::uint8_t>(bound.cache_bytes()));
 assert(bound.bind(workspace.data(),bound.workspace_bytes(),cache.memory())==ModelStatus::OK);
 assert(bound.repack_lut8()==ModelStatus::MEMORY && p.bytes==source);
 std::puts("Native MKA repack PASS: nibble/plane/mixed bytes and CRC match Python; idempotent, readonly/bound rejection, cancellation and read/write faults PASS");
}
