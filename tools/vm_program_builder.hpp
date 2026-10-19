#pragma once
// Host tooling only. The on-device reader/executor uses caller-owned bounded
// buffers; std::vector/map and source-sized allocations never enter firmware.
#include "language_linked_program.hpp"
#include "mk8_codec.hpp"
#include <algorithm>
#include <array>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
namespace vm_program_builder {
using Bytes=std::vector<uint8_t>;
struct Disk {
  std::array<std::map<uint32_t,std::array<uint8_t,language_vm::flash::WRITE_BYTES>>,4> pages;
  static bool read(void* raw,language_vm::flash::Space space,uint32_t at,uint8_t* out,uint16_t n) {
    auto& d=*(Disk*)raw;
    while(n) {
      auto page=d.pages[space].find(at/language_vm::flash::WRITE_BYTES);
      if(page==d.pages[space].end())return false;
      unsigned inside=at%language_vm::flash::WRITE_BYTES,count=std::min<unsigned>(n,language_vm::flash::WRITE_BYTES-inside);
      memcpy(out,page->second.data()+inside,count);at+=count;out+=count;n=uint16_t(n-count);
    }
    return true;
  }
  static bool write(void* raw,language_vm::flash::Space space,uint32_t at,const uint8_t* in,uint16_t n) {
    if(at%language_vm::flash::WRITE_BYTES || n!=language_vm::flash::WRITE_BYTES)return false;
    memcpy(((Disk*)raw)->pages[space][at/language_vm::flash::WRITE_BYTES].data(),in,n);return true;
  }
  static bool truncate(void* raw,language_vm::flash::Space space,uint32_t n) {
    if(n)return false;((Disk*)raw)->pages[space].clear();return true;
  }
  language_vm::flash::IO io(){return {this,read,write,truncate};}
};
inline Bytes compile(language_vm::Language language,const std::string& utf8) {
  Bytes source(utf8.size()+1);usize length=0;
  if(!mk8::from_utf8((const uint8_t*)utf8.data(),utf8.size(),source.data(),source.size()-1,length) ||
     !length || length>language_vm::source::MAX_SIZE)throw std::runtime_error("invalid M8/source size");
  Disk disk;language_vm::source::Reader input((const char*)source.data(),uint16_t(length));
  alignas(8) uint8_t scratch[language_vm::FLASH_COMPILER_WORKSPACE_SIZE];
  const auto result=language_vm::compile_flash_source(language,input,disk.io(),true,scratch+language_vm::FLASH_FRONTEND_BYTES);
  if(result.error!=language_vm::Error::NONE)throw std::runtime_error(std::string(language_vm::error_name(result.error))+" at line "+std::to_string(result.line));
  Bytes out(result.size);
  for(uint32_t at=0;at<out.size();) {
    const auto n=uint16_t(std::min<size_t>(1024,out.size()-at));
    if(!Disk::read(&disk,language_vm::flash::IMAGE,at,out.data()+at,n))throw std::runtime_error("compiled image read failed");at+=n;
  }
  return out;
}
struct Member {uint32_t symbol;uint16_t source_id;Bytes image;};
inline Bytes package(std::vector<Member> members,uint32_t entry) {
  using namespace language_vm;
  if(members.empty() || members.size()>linked::MAX_MEMBERS)throw std::runtime_error("member count");
  std::sort(members.begin(),members.end(),[](const Member& a,const Member& b){return a.symbol<b.symbol;});
  Bytes out(linked::HEADER_BYTES+members.size()*linked::ENTRY_BYTES);
  memcpy(out.data(),"LVP1",4);out[4]=linked::VERSION;flash::word(out.data()+6,uint16_t(members.size()));
  flash::dword(out.data()+12,entry);flash::dword(out.data()+16,uint32_t(members.size()*linked::ENTRY_BYTES));
  std::vector<uint32_t> offsets;bool found=false;uint32_t previous=0;
  for(unsigned i=0;i<members.size();++i) {
    const auto& member=members[i];if(!member.symbol || member.symbol==previous)throw std::runtime_error("duplicate/zero symbol");
    previous=member.symbol;found=found || member.symbol==entry;
    unsigned alias=0;
    while(alias<i && (members[alias].source_id!=member.source_id || members[alias].image!=member.image))++alias;
    const uint32_t offset=alias<i?offsets[alias]:uint32_t(out.size());offsets.push_back(offset);
    if(member.image.size()>UINT32_MAX-out.size())throw std::runtime_error("package too large");
    auto* record=out.data()+linked::HEADER_BYTES+i*linked::ENTRY_BYTES;
    flash::dword(record,member.symbol);flash::dword(record+4,offset);
    flash::dword(record+8,uint32_t(member.image.size()));flash::dword(record+12,member.source_id);
    if(alias==i)out.insert(out.end(),member.image.begin(),member.image.end());
  }
  if(!found)throw std::runtime_error("missing entry symbol");
  flash::dword(out.data()+8,uint32_t(out.size()));
  flash::dword(out.data()+24,checksum(out.data()+linked::HEADER_BYTES,out.size()-linked::HEADER_BYTES));
  flash::dword(out.data()+28,checksum(out.data(),28));return out;
}
}
